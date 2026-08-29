"""Agreeing a fare between a passenger and a driver, section 89.

Three moves: a passenger asks at a price, drivers answer with a price, the
passenger picks one. Nothing here computes a fare -- VELRO does not know the
distance between two villages in Ghorband or which stretch of road is dirt, and
inventing a number would be worse than asking the two people who do know.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from domain.enums import ActorRole, FareOfferStatus, RideRequestStatus
from domain.negotiation import FareOffer, assert_offer_allowed
from shared import error_codes
from shared.clock import Clock
from shared.errors import ConflictError, NotFoundError, PermissionError
from shared.ids import IdGenerator
from shared.money import Money

# How long a request stays on the drivers' board. Long enough for someone to
# finish a journey and look, short enough that a passenger is not still being
# offered a ride they gave up on an hour ago.
DEFAULT_REQUEST_TTL_MINUTES = 45


@dataclass(frozen=True, slots=True)
class RequestRideCommand:
    passenger_id: str
    origin_station_id: str
    destination_id: str
    passenger_count: int
    offered_fare_minor: int
    currency: str = "AFN"
    vehicle_type_code: str | None = None
    note: str | None = None
    requested_for: datetime | None = None
    request_id: str | None = None


class RequestRide:
    """The passenger names a price."""

    def __init__(
        self, *, requests, geography, settings, audit, clock: Clock, new_id: IdGenerator
    ) -> None:
        self._requests = requests
        self._geography = geography
        self._settings = settings
        self._audit = audit
        self._clock = clock
        self._new_id = new_id

    def execute(self, cmd: RequestRideCommand):
        if cmd.offered_fare_minor <= 0:
            raise ConflictError(
                error_codes.FARE_OFFER_AMOUNT_INVALID,
                amount_minor=cmd.offered_fare_minor,
            )
        if self._geography.find_station(cmd.origin_station_id) is None:
            raise NotFoundError(
                error_codes.STATION_NOT_FOUND, station_id=cmd.origin_station_id
            )
        if self._geography.find_destination(cmd.destination_id) is None:
            raise NotFoundError(
                error_codes.DESTINATION_NOT_FOUND, destination_id=cmd.destination_id
            )

        now = self._clock.now()
        # One open request at a time. A passenger with three live requests is
        # taking three drivers off the board for one journey.
        #
        # ``at`` is what stops a request nobody answered from blocking them for
        # ever: the row may still say OPEN until someone reads it, but a
        # deadline that has passed does not hold a place.
        if self._requests.find_open_for_passenger(cmd.passenger_id, at=now) is not None:
            raise ConflictError(error_codes.BOOKING_LIMIT_REACHED, limit=1)
        ttl = self._settings.get_int(
            "ride_request.ttl_minutes", DEFAULT_REQUEST_TTL_MINUTES
        )
        row = self._requests.create(
            id=self._new_id(),
            passenger_id=cmd.passenger_id,
            origin_station_id=cmd.origin_station_id,
            destination_id=cmd.destination_id,
            passenger_count=cmd.passenger_count,
            vehicle_type_code=cmd.vehicle_type_code,
            requested_for=cmd.requested_for or now,
            expires_at=now + timedelta(minutes=ttl),
            status=RideRequestStatus.OPEN.value,
            offered_fare_minor=cmd.offered_fare_minor,
            offered_fare_currency=cmd.currency,
            note=cmd.note,
        )
        self._audit.write(
            "ride_request.created",
            actor_id=cmd.passenger_id,
            actor_role=ActorRole.PASSENGER,
            entity_type="ride_request",
            entity_id=row.id,
            after={
                "offered_fare_minor": cmd.offered_fare_minor,
                "currency": cmd.currency,
                "passengers": cmd.passenger_count,
            },
            request_id=cmd.request_id,
        )
        return row


@dataclass(frozen=True, slots=True)
class OfferFareCommand:
    ride_request_id: str
    driver_user_id: str
    amount_minor: int
    note: str | None = None
    request_id: str | None = None


class OfferFare:
    """A driver answers with a price.

    A driver happy with the asking price offers exactly that number. There is no
    separate "accept": one path means one set of rules, and the passenger's list
    reads the same whether a driver agreed or countered.
    """

    def __init__(
        self, *, requests, offers, drivers, vehicles, audit, clock: Clock,
        new_id: IdGenerator,
    ) -> None:
        self._requests = requests
        self._offers = offers
        self._drivers = drivers
        self._vehicles = vehicles
        self._audit = audit
        self._clock = clock
        self._new_id = new_id

    def execute(self, cmd: OfferFareCommand) -> FareOffer:
        driver = self._drivers.find_by_user(cmd.driver_user_id)
        if driver is None:
            raise NotFoundError(
                error_codes.DRIVER_NOT_FOUND, user_id=cmd.driver_user_id
            )
        row = self._requests.find(cmd.ride_request_id)
        if row is None:
            raise NotFoundError(
                error_codes.RIDE_REQUEST_NOT_FOUND, ride_request_id=cmd.ride_request_id
            )

        now = self._clock.now()
        # An expired request is closed the moment anyone looks at it, rather
        # than waiting for a job that may not have run.
        status = RideRequestStatus(row.status)
        if status is RideRequestStatus.OPEN and row.expires_at <= now:
            row.status = RideRequestStatus.EXPIRED.value
            self._requests.save(row)
            status = RideRequestStatus.EXPIRED

        asking = Money(row.offered_fare_minor, row.offered_fare_currency)
        offered = Money(cmd.amount_minor, row.offered_fare_currency)
        assert_offer_allowed(
            asking=asking,
            offered=offered,
            request_status=status,
            already_offered=self._offers.open_for(row.id, driver.id) is not None,
            driver_is_passenger=row.passenger_id == cmd.driver_user_id,
        )

        vehicle = self._vehicles.current_for_driver(driver.id)
        created = self._offers.create(
            id=self._new_id(),
            ride_request_id=row.id,
            driver_id=driver.id,
            vehicle_id=vehicle.id if vehicle else None,
            amount_minor=offered.amount_minor,
            amount_currency=offered.currency,
            status=FareOfferStatus.OFFERED.value,
            note=cmd.note,
        )
        self._audit.write(
            "fare_offer.made",
            actor_id=cmd.driver_user_id,
            actor_role=ActorRole.DRIVER,
            entity_type="fare_offer",
            entity_id=created.id,
            after={
                "ride_request_id": row.id,
                "amount_minor": offered.amount_minor,
                "asking_minor": asking.amount_minor,
            },
            request_id=cmd.request_id,
        )
        return _to_offer(created)


@dataclass(frozen=True, slots=True)
class WithdrawOfferCommand:
    offer_id: str
    driver_user_id: str
    request_id: str | None = None


class WithdrawOffer:
    def __init__(self, *, offers, drivers, audit, clock: Clock) -> None:
        self._offers = offers
        self._drivers = drivers
        self._audit = audit
        self._clock = clock

    def execute(self, cmd: WithdrawOfferCommand) -> FareOffer:
        driver = self._drivers.find_by_user(cmd.driver_user_id)
        row = self._offers.find(cmd.offer_id)
        if row is None or driver is None or row.driver_id != driver.id:
            # The same answer whether it is someone else's or does not exist.
            raise NotFoundError(error_codes.FARE_OFFER_NOT_FOUND, offer_id=cmd.offer_id)

        offer = _to_offer(row)
        offer.withdraw(at=self._clock.now())
        row.status = offer.status.value
        row.responded_at = offer.responded_at
        row.version += 1
        self._offers.save(row)

        self._audit.write(
            "fare_offer.withdrawn",
            actor_id=cmd.driver_user_id,
            actor_role=ActorRole.DRIVER,
            entity_type="fare_offer",
            entity_id=row.id,
            request_id=cmd.request_id,
        )
        return offer


def _to_offer(row) -> FareOffer:
    return FareOffer(
        id=row.id,
        ride_request_id=row.ride_request_id,
        driver_id=row.driver_id,
        amount=Money(row.amount_minor, row.amount_currency),
        status=row.status,
        note=row.note,
        created_at=row.created_at,
        responded_at=row.responded_at,
    )


@dataclass(frozen=True, slots=True)
class AcceptOfferCommand:
    offer_id: str
    passenger_id: str
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class AcceptOfferResult:
    ride_request_id: str
    offer_id: str
    trip_id: str
    trip_number: str
    booking_id: str
    booking_number: str
    verification_code: str
    driver_id: str
    agreed_fare: Money


class AcceptOffer:
    """The passenger picks a driver, and the journey exists.

    This is the moment the fare is settled, so it is also the moment everything
    downstream is fixed: the trip, the seats, the booking, and the agreed amount
    copied onto the booking. A price agreed today must still explain a receipt
    read next month, so nothing here leaves the fare to be looked up again.
    """

    def __init__(
        self, *, requests, offers, trips, bookings, seats, drivers, vehicles,
        routes, geography, numbers, codes, audit, clock: Clock, new_id: IdGenerator,
    ) -> None:
        self._requests = requests
        self._offers = offers
        self._trips = trips
        self._bookings = bookings
        self._seats = seats
        self._drivers = drivers
        self._vehicles = vehicles
        self._routes = routes
        self._geography = geography
        self._numbers = numbers
        self._codes = codes
        self._audit = audit
        self._clock = clock
        self._new_id = new_id

    def execute(self, cmd: AcceptOfferCommand) -> AcceptOfferResult:
        from domain.booking import Booking
        from domain.enums import BookingStatus, RideKind, SeatStatus, TripStatus
        from domain.fare import FareComponent, FareQuote

        offer_row = self._offers.find(cmd.offer_id)
        if offer_row is None:
            raise NotFoundError(error_codes.FARE_OFFER_NOT_FOUND, offer_id=cmd.offer_id)
        request_row = self._requests.find(offer_row.ride_request_id)
        if request_row is None:
            raise NotFoundError(
                error_codes.RIDE_REQUEST_NOT_FOUND,
                ride_request_id=offer_row.ride_request_id,
            )
        if request_row.passenger_id != cmd.passenger_id:
            raise PermissionError(
                error_codes.PERMISSION_DENIED, offer_id=cmd.offer_id
            )

        now = self._clock.now()
        if RideRequestStatus(request_row.status) is not RideRequestStatus.OPEN:
            raise ConflictError(
                error_codes.RIDE_REQUEST_NOT_OPEN, current=request_row.status
            )

        offer = _to_offer(offer_row)
        offer.accept(at=now)

        driver = self._drivers.find(offer_row.driver_id)
        if driver is None:
            raise NotFoundError(
                error_codes.DRIVER_NOT_FOUND, driver_id=offer_row.driver_id
            )
        vehicle = self._vehicles.current_for_driver(driver.id)
        # Seats come from the vehicle when there is one: a Corolla cannot carry
        # a Hiace's worth of passengers because a request asked for it.
        capacity = max(
            request_row.passenger_count, vehicle.seat_capacity if vehicle else 0
        )

        route = self._routes.find_for(
            request_row.origin_station_id, request_row.destination_id
        )
        trip = self._trips.create(
            id=self._new_id(),
            number=self._numbers.allocate("trip", year=now.year),
            route_id=route.id if route else None,
            ride_kind=RideKind.PRIVATE.value,
            seat_capacity=capacity,
            scheduled_departure_at=request_row.requested_for,
            status=TripStatus.DRIVER_ASSIGNED.value,
            origin_station_id=request_row.origin_station_id,
            destination_id=request_row.destination_id,
            driver_id=driver.id,
            vehicle_id=vehicle.id if vehicle else None,
        )
        self._trips.session.flush()

        # Seats are rows, so capacity cannot be exceeded by construction --
        # the same guarantee a scheduled trip has.
        for n in range(1, capacity + 1):
            self._seats.create(
                id=self._new_id(), trip_id=trip.id, seat_number=n,
                status=SeatStatus.AVAILABLE.value,
            )
        self._trips.session.flush()

        # Through lock_available and reserve, exactly as a scheduled booking
        # goes. There is no contention on a trip created a line ago, but two
        # ways of taking a seat would mean two places for the guarantee to be
        # weakened later, and this is the mechanic the product rests on.
        taken = self._seats.lock_available(trip.id, request_row.passenger_count)

        agreed = Money(offer_row.amount_minor, offer_row.amount_currency)
        # A quote of exactly one line, and that line says the price was agreed
        # rather than calculated. Going through FareQuote rather than building a
        # Booking by hand keeps one construction path, so the negotiated booking
        # is frozen and validated exactly as a scheduled one is.
        quote = FareQuote(
            components=(
                FareComponent(key="fare.component.agreed", amount=agreed, quantity=1),
            ),
            currency=agreed.currency,
            ride_kind=RideKind.PRIVATE,
            seat_count=request_row.passenger_count,
            route_id=route.id if route else None,
            from_sequence=0,
            to_sequence=1,
        )
        booking = Booking.from_quote(
            id=self._new_id(),
            number=self._numbers.allocate("booking", year=now.year),
            trip_id=trip.id,
            passenger_id=cmd.passenger_id,
            quote=quote,
            seat_ids=[s.id for s in taken],
            seat_numbers=[s.seat_number for s in taken],
            pickup_station_id=request_row.origin_station_id,
            dropoff_destination_id=request_row.destination_id,
            verification_code=self._codes.generate(),
        )
        booking.transition_to(BookingStatus.CONFIRMED, at=now)
        # The driver is already agreed -- that is what accepting the offer
        # meant -- so the booking says so rather than showing "awaiting driver".
        booking.transition_to(BookingStatus.DRIVER_ASSIGNED, at=now)
        booking_row = self._bookings.create(
            id=booking.id,
            number=booking.number,
            trip_id=trip.id,
            passenger_id=cmd.passenger_id,
            ride_kind=booking.ride_kind.value,
            seat_count=booking.seat_count,
            pickup_sequence=0,
            dropoff_sequence=1,
            pickup_station_id=request_row.origin_station_id,
            dropoff_destination_id=request_row.destination_id,
            fare_total_minor=agreed.amount_minor,
            fare_total_currency=agreed.currency,
            fare_breakdown=list(booking.fare_breakdown),
            status=booking.status.value,
            verification_code=booking.verification_code,
            confirmed_at=now,
        )
        self._bookings.session.flush()

        self._seats.reserve(taken, booking_row.id)

        request_row.status = RideRequestStatus.MATCHED.value
        request_row.trip_id = trip.id
        request_row.agreed_fare_minor = agreed.amount_minor
        request_row.accepted_offer_id = offer_row.id
        request_row.version += 1
        self._requests.save(request_row)

        offer_row.status = offer.status.value
        offer_row.responded_at = now
        offer_row.version += 1
        self._offers.save(offer_row)
        # Every other driver is told at once rather than left refreshing a
        # request that is already taken.
        self._offers.decline_others(request_id=request_row.id, except_id=offer_row.id, at=now)

        self._audit.write(
            "fare_offer.accepted",
            actor_id=cmd.passenger_id,
            actor_role=ActorRole.PASSENGER,
            entity_type="fare_offer",
            entity_id=offer_row.id,
            after={
                "trip_id": trip.id,
                "booking_id": booking_row.id,
                "agreed_minor": agreed.amount_minor,
                "currency": agreed.currency,
                "driver_id": driver.id,
            },
            request_id=cmd.request_id,
        )
        return AcceptOfferResult(
            ride_request_id=request_row.id,
            offer_id=offer_row.id,
            trip_id=trip.id,
            trip_number=trip.number,
            booking_id=booking_row.id,
            booking_number=booking_row.number,
            verification_code=booking_row.verification_code,
            driver_id=driver.id,
            agreed_fare=agreed,
        )
