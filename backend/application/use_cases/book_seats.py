"""Book seats on a trip.

This use case owns the transaction. Everything inside it commits together or
not at all: the seats are claimed, the booking is written, its number is
allocated from the sequence, and the audit entry is recorded -- in one
transaction, so there is no state in which a passenger holds a seat that no
booking records, or a booking exists for seats nobody holds.

Ordering matters and is deliberate:

  1. Read the trip and validate what can be validated cheaply.
  2. Lock the seats. This is the point of contention and it happens as late as
     possible, so a lock is never held across a fare lookup.
  3. Write the booking, then bind the seats to it.
  4. Audit.

The seat lock is held from step 2 until the transaction ends. Anything slow
placed between 2 and 4 would serialise every booking on that trip behind it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from application.ports.repositories import (
    BookingRepository,
    RouteRepository,
    TripRepository,
    TripSeatRepositoryPort,
)
from application.ports.services import (
    AuditLog,
    NumberAllocator,
    SettingsProvider,
    VerificationCodeGenerator,
)
from application.pricing.fixed import FareRequest
from domain.booking import Booking
from domain.enums import ActorRole, BookingStatus, PaymentMethod, RideKind, TripStatus
from domain.trip import BOOKABLE_TRIP_STATUSES, Trip, TripSeat
from shared import error_codes
from shared.clock import Clock
from shared.errors import ConflictError, ValidationError
from shared.ids import IdGenerator
from shared.money import Money

SETTING_MAX_ACTIVE_BOOKINGS = "booking.max_active_per_passenger"
SETTING_MAX_SEATS_PER_BOOKING = "booking.max_seats_per_booking"
#: Minutes before departure at which booking closes. Zero closes it at the
#: departure time itself, which is the floor: a seat is never sold on a
#: vehicle whose scheduled departure has already passed.
SETTING_CUTOFF_MINUTES = "booking.cutoff_minutes"


@dataclass(frozen=True, slots=True)
class BookSeatsCommand:
    trip_id: str
    passenger_id: str
    seat_count: int
    pickup_station_id: str
    dropoff_destination_id: str
    payment_method: PaymentMethod = PaymentMethod.CASH
    passenger_note: str | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class BookSeatsResult:
    booking_id: str
    number: str
    seat_numbers: list[int]
    fare_total: Money
    verification_code: str
    status: BookingStatus


class BookSeats:
    def __init__(
        self,
        *,
        trips: TripRepository,
        seats: TripSeatRepositoryPort,
        bookings: BookingRepository,
        routes: RouteRepository,
        fare_strategy,
        numbers: NumberAllocator,
        codes: VerificationCodeGenerator,
        settings: SettingsProvider,
        audit: AuditLog,
        clock: Clock,
        new_id: IdGenerator,
    ) -> None:
        self._trips = trips
        self._seats = seats
        self._bookings = bookings
        self._routes = routes
        self._fares = fare_strategy
        self._numbers = numbers
        self._codes = codes
        self._settings = settings
        self._audit = audit
        self._clock = clock
        self._new_id = new_id

    def execute(self, cmd: BookSeatsCommand) -> BookSeatsResult:
        now = self._clock.now()

        # -- 1. cheap validation, before anything is locked -----------------
        max_seats = self._settings.get_int(SETTING_MAX_SEATS_PER_BOOKING, 4)
        if not 1 <= cmd.seat_count <= max_seats:
            raise ValidationError(
                error_codes.BOOKING_SEAT_COUNT_INVALID,
                seat_count=cmd.seat_count,
                maximum=max_seats,
            )

        max_active = self._settings.get_int(SETTING_MAX_ACTIVE_BOOKINGS, 5)
        if self._bookings.count_active_for_passenger(cmd.passenger_id) >= max_active:
            raise ConflictError(
                error_codes.BOOKING_LIMIT_REACHED,
                passenger_id=cmd.passenger_id,
                maximum=max_active,
            )

        trip_row = self._trips.get(cmd.trip_id)
        trip = _to_trip(trip_row, self._seats.list_for_trip(cmd.trip_id))
        closes_before = timedelta(minutes=self._settings.get_int(SETTING_CUTOFF_MINUTES, 0))
        trip.assert_bookable(cmd.seat_count, at=now, closes_before=closes_before)

        route = self._routes.get(trip.route_id)
        stops = self._routes.stops_of(trip.route_id)
        from_seq, to_seq = _resolve_segment(
            stops, cmd.pickup_station_id, cmd.dropoff_destination_id, route_id=route.id
        )

        # -- 2. price before locking, so no lock spans this lookup ----------
        quote = self._fares.quote(
            FareRequest(
                route_id=route.id,
                ride_kind=RideKind(trip.ride_kind),
                from_sequence=from_seq,
                to_sequence=to_seq,
                seat_count=cmd.seat_count,
                on=now.date(),
                vehicle_type_code=None,
            )
        )

        # -- 3. the contended step ------------------------------------------
        # The trip row first, then its seats, in that order everywhere. The
        # bookable check in step 1 was optimistic and unlocked, so a departure
        # committing in this window would otherwise sell a seat on a vehicle
        # that has already left; AdvanceTrip takes the same lock, so the two
        # serialise and the check below is true at commit, not merely at read.
        trip_row = self._trips.lock(cmd.trip_id)
        if (
            trip_row is None
            or TripStatus(trip_row.status) not in BOOKABLE_TRIP_STATUSES
            # The clock again, against the locked row: true at commit, not
            # merely at the read a moment ago.
            or now >= trip_row.scheduled_departure_at - closes_before
        ):
            raise ConflictError(
                error_codes.TRIP_DEPARTED,
                trip_id=cmd.trip_id,
                status=trip_row.status if trip_row else "?",
            )
        locked = self._seats.lock_available(cmd.trip_id, cmd.seat_count)

        booking_id = self._new_id()
        number = self._numbers.allocate("booking", year=now.year)
        booking = Booking.from_quote(
            id=booking_id,
            number=number,
            trip_id=cmd.trip_id,
            passenger_id=cmd.passenger_id,
            quote=quote,
            seat_ids=[s.id for s in locked],
            seat_numbers=[s.seat_number for s in locked],
            pickup_station_id=cmd.pickup_station_id,
            dropoff_destination_id=cmd.dropoff_destination_id,
            verification_code=self._codes.generate(),
            payment_method=cmd.payment_method,
            passenger_note=cmd.passenger_note,
        )
        # A trip that already has a driver hands the booking that status
        # immediately, so a passenger booking onto a departing vehicle is not
        # briefly shown as "awaiting driver".
        booking.transition_to(BookingStatus.CONFIRMED, at=now)
        if trip.status is not TripStatus.SCHEDULED and trip.driver_id:
            booking.transition_to(BookingStatus.DRIVER_ASSIGNED, at=now)

        self._bookings.create(
            id=booking.id,
            number=booking.number,
            trip_id=booking.trip_id,
            passenger_id=booking.passenger_id,
            ride_kind=booking.ride_kind.value,
            seat_count=booking.seat_count,
            pickup_sequence=booking.pickup_sequence,
            dropoff_sequence=booking.dropoff_sequence,
            pickup_station_id=booking.pickup_station_id,
            dropoff_destination_id=booking.dropoff_destination_id,
            fare_total_minor=booking.fare_total.amount_minor,
            fare_total_currency=booking.fare_total.currency,
            fare_breakdown=list(booking.fare_breakdown),
            fare_rule_id=quote.fare_rule_id,
            status=booking.status.value,
            verification_code=booking.verification_code,
            payment_method=booking.payment_method.value,
            passenger_note=booking.passenger_note,
            confirmed_at=booking.confirmed_at,
        )
        # The booking must exist before the seats can point at it: booking_seats
        # carries a foreign key, and the unique constraint on it is the whole
        # guarantee.
        self._bookings.flush()
        self._seats.reserve(locked, booking.id)

        # -- 4. audit, in the same transaction ------------------------------
        self._audit.write(
            "booking.created",
            actor_id=cmd.passenger_id,
            actor_role=ActorRole.PASSENGER,
            entity_type="booking",
            entity_id=booking.id,
            after={
                "number": booking.number,
                "trip_id": booking.trip_id,
                "seat_numbers": booking.seat_numbers,
                "fare_total_minor": booking.fare_total.amount_minor,
                "currency": booking.fare_total.currency,
            },
            request_id=cmd.request_id,
        )

        return BookSeatsResult(
            booking_id=booking.id,
            number=booking.number,
            seat_numbers=booking.seat_numbers,
            fare_total=booking.fare_total,
            verification_code=booking.verification_code,
            status=booking.status,
        )


def _resolve_segment(
    stops, pickup_station_id: str, dropoff_destination_id: str, *, route_id: str
) -> tuple[int, int]:
    """Locate the leg the passenger is buying, in travelling order.

    Boarding at an intermediate station is normal on these routes, so the check
    is 'both present, pickup before dropoff' rather than 'matches the endpoints'.
    """
    by_place: dict[str, tuple[int, bool, bool]] = {}
    for stop in stops:
        place = stop.station_id or stop.destination_id
        by_place[place] = (stop.sequence, stop.is_pickup, stop.is_dropoff)

    origin = by_place.get(pickup_station_id)
    destination = by_place.get(dropoff_destination_id)
    if origin is None or destination is None or origin[0] >= destination[0]:
        raise ConflictError(
            error_codes.ROUTE_NOT_RESOLVABLE,
            route_id=route_id,
            origin=pickup_station_id,
            destination=dropoff_destination_id,
        )
    if not origin[1]:
        raise ConflictError(error_codes.STATION_DISABLED, station_id=pickup_station_id)
    if not destination[2]:
        raise ConflictError(
            error_codes.DESTINATION_DISABLED, destination_id=dropoff_destination_id
        )
    return origin[0], destination[0]


def _to_trip(row, seat_rows) -> Trip:
    """ORM row -> domain entity. ORM objects never escape infrastructure."""
    return Trip(
        id=row.id,
        number=row.number,
        route_id=row.route_id,
        ride_kind=RideKind(row.ride_kind),
        seat_capacity=row.seat_capacity,
        scheduled_departure_at=row.scheduled_departure_at,
        status=TripStatus(row.status),
        origin_station_id=row.origin_station_id,
        destination_id=row.destination_id,
        driver_id=row.driver_id,
        vehicle_id=row.vehicle_id,
        seats=[
            TripSeat(
                id=s.id,
                trip_id=s.trip_id,
                seat_number=s.seat_number,
                status=s.status,
                booking_id=s.booking_id,
                version=s.version,
            )
            for s in seat_rows
        ],
    )
