"""Driving a trip through its states.

One use case for the whole progression rather than one per transition: the
transition table already says what is legal, and the work that accompanies each
step -- cascading booking statuses, freeing the driver, settling money -- is the
part worth writing once.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from domain.booking import Booking
from domain.enums import (
    ActorRole,
    BookingStatus,
    DriverAvailability,
    PaymentMethod,
    PaymentStatus,
    RideKind,
    TripStatus,
)
from domain.fare import CommissionSplit
from domain.lifecycles import TRIP_TO_BOOKING_STATUS
from domain.trip import Trip, TripSeat
from shared import error_codes
from shared.clock import Clock
from shared.errors import NotFoundError, ConflictError, PermissionError
from shared.ids import IdGenerator
from shared.logging import get_logger
from shared.money import DEFAULT_CURRENCY, Money


@dataclass(frozen=True, slots=True)
class AdvanceTripCommand:
    trip_id: str
    target: TripStatus
    actor_id: str
    actor_role: ActorRole
    # Only read when target is CANCELLED.
    reason_code: str = "DRIVER_CANCELLED"
    note: str | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class AdvanceTripResult:
    trip_id: str
    status: TripStatus
    bookings_advanced: int
    driver_earning: Money | None = None
    platform_commission: Money | None = None


log = get_logger(__name__)


class AdvanceTrip:
    def __init__(
        self,
        *,
        trips,
        seats,
        bookings,
        drivers,
        payments,
        commissions,
        wallets,
        settings,
        audit,
        clock: Clock,
        new_id: IdGenerator,
        notifier=None,
        cancellations=None,
    ) -> None:
        self._trips = trips
        self._seats = seats
        self._bookings = bookings
        self._drivers = drivers
        self._payments = payments
        self._commissions = commissions
        self._wallets = wallets
        self._settings = settings
        self._audit = audit
        self._clock = clock
        self._new_id = new_id
        self._notifier = notifier
        self._cancellations = cancellations

    def execute(self, cmd: AdvanceTripCommand) -> AdvanceTripResult:
        now = self._clock.now()
        # Locked: book_seats takes this row before touching seats, so a
        # departure and a booking can no longer both pass their checks in the
        # same instant -- whichever runs second sees the other's write.
        row = self._trips.lock(cmd.trip_id)
        if row is None:
            raise NotFoundError(self._trips.not_found_code, id=cmd.trip_id)

        trip = _to_trip(row, self._seats.list_for_trip(row.id))
        previous = trip.status

        # A driver may only move their own trip. An admin may move any, and the
        # audit entry records which of the two happened.
        if cmd.actor_role is ActorRole.DRIVER:
            driver = self._drivers.find_by_user(cmd.actor_id)
            if driver is None or trip.driver_id != driver.id:
                raise PermissionError(
                    error_codes.PERMISSION_DENIED, trip_id=trip.id, actor_id=cmd.actor_id
                )

        trip.transition_to(cmd.target, at=now)

        row.status = trip.status.value
        row.started_at = trip.started_at
        row.completed_at = trip.completed_at
        row.cancelled_at = trip.cancelled_at
        self._trips.save(row)

        if trip.status in _CALLED_OFF:
            self._record_cancellation(trip, row, cmd)

        advanced = self._cascade_bookings(trip, now)
        self._update_driver_availability(trip, now)

        earning = commission = None
        if cmd.target is TripStatus.COMPLETED:
            earning, commission = self._settle(trip, row, now, cmd)

        self._audit.write(
            f"trip.{cmd.target.value.lower()}",
            actor_id=cmd.actor_id,
            actor_role=cmd.actor_role,
            entity_type="trip",
            entity_id=trip.id,
            before={"status": previous.value},
            after={"status": trip.status.value},
            request_id=cmd.request_id,
        )
        return AdvanceTripResult(
            trip_id=trip.id,
            status=trip.status,
            bookings_advanced=advanced,
            driver_earning=earning,
            platform_commission=commission,
        )

    def _record_cancellation(self, trip: Trip, row, cmd: AdvanceTripCommand) -> None:
        """One row per booking left holding the bag.

        A cancellation with no recorded reason cannot be told from any other. A
        driver whose car broke down and one who simply changed their mind look
        identical afterwards -- and the second is the one that costs a passenger
        a morning, and the one a suspension has to be able to point at.

        Written per booking rather than per trip so a shared ride that strands
        four passengers is four cancellations, which is what it was.
        """
        if self._cancellations is None:
            return
        for booking_row in self._bookings.active_for_trip(trip.id):
            self._cancellations.create(
                id=self._new_id(),
                trip_id=trip.id,
                booking_id=booking_row.id,
                cancelled_by_user_id=cmd.actor_id,
                cancelled_by_role=cmd.actor_role.value,
                reason_code=cmd.reason_code,
                note=cmd.note,
                # No fee. The passenger did not cancel; the ride was taken away
                # from them, and charging for that would be indefensible.
                fee_minor=0,
                fee_currency=DEFAULT_CURRENCY,
            )

    # -- cascades ---------------------------------------------------------

    def _cascade_bookings(self, trip: Trip, now: datetime) -> int:
        # Read the passengers before the cascade, not after: cancelling their
        # bookings takes them out of active_for_trip, so a list gathered
        # afterwards is empty. The same shape of mistake as the losing-driver
        # notification, which failed silently for exactly this reason.
        riders = (
            [(row.id, row.number, row.passenger_id)
             for row in self._bookings.active_for_trip(trip.id)]
            if trip.status in _CALLED_OFF else []
        )

        advanced = cascade_bookings(self._bookings, trip.status, now, trip_id=trip.id)

        for booking_id, number, passenger_id in riders:
            # Cancelling a booking silently leaves someone standing at a
            # roadside watching for a vehicle. The row is the record; delivery
            # is best effort on top of it.
            _tell(
                self._notifier,
                user_id=passenger_id,
                message_key="notify.trip.cancelled",
                payload={"booking_number": number, "trip_status": trip.status.value},
                trip_id=trip.id,
                booking_id=booking_id,
            )
        return advanced

    def _update_driver_availability(self, trip: Trip, now: datetime) -> None:
        if trip.driver_id is None:
            return
        driver = self._drivers.get(trip.driver_id)
        if trip.status in (
            TripStatus.DRIVER_ASSIGNED, TripStatus.DRIVER_ARRIVING,
            TripStatus.ARRIVED_AT_PICKUP, TripStatus.BOARDING, TripStatus.IN_TRANSIT,
        ):
            driver.availability = DriverAvailability.ON_TRIP.value
        elif trip.status in (TripStatus.COMPLETED, TripStatus.CANCELLED):
            # Back to ONLINE, not OFFLINE: a driver who just finished a trip is
            # still working, and sending them offline would drop them out of
            # dispatch until they noticed.
            driver.availability = DriverAvailability.ONLINE.value
            if trip.status is TripStatus.COMPLETED:
                driver.completed_trips += 1
        self._drivers.save(driver)

    # -- money ------------------------------------------------------------

    def _settle(
        self, trip: Trip, row, now: datetime, cmd: AdvanceTripCommand
    ) -> tuple[Money | None, Money | None]:
        """Record payment, split commission and credit the driver's wallet.

        Runs inside the same transaction as the trip completion, so a completed
        trip always has its money recorded. Cash is collected by the driver
        directly, so the payment is marked collected at completion; a future
        online method would leave it PENDING until the provider confirms.
        """
        if trip.driver_id is None:
            return None, None

        rate = self._settings.get_int("commission.rate_basis_points", 1000)
        wallet = self._wallets.get_or_create(trip.driver_id, "AFN")

        total_driver = Money.zero(wallet.currency)
        total_platform = Money.zero(wallet.currency)

        for booking_row in self._bookings.list_for_trip(trip.id):
            if booking_row.status != BookingStatus.COMPLETED.value:
                continue
            if self._commissions.find_for_booking(booking_row.id) is not None:
                continue    # idempotent: completing twice must not pay twice

            gross = Money(booking_row.fare_total_minor, booking_row.fare_total_currency)
            split = CommissionSplit.of(gross, rate)

            if self._payments.find_for_booking(booking_row.id) is None:
                self._payments.create(
                    id=self._new_id(),
                    booking_id=booking_row.id,
                    trip_id=trip.id,
                    method=booking_row.payment_method,
                    status=(
                        PaymentStatus.COLLECTED.value
                        if booking_row.payment_method == PaymentMethod.CASH.value
                        else PaymentStatus.PENDING.value
                    ),
                    amount_minor=gross.amount_minor,
                    amount_currency=gross.currency,
                    collected_at=(
                        now
                        if booking_row.payment_method == PaymentMethod.CASH.value
                        else None
                    ),
                    collected_by=trip.driver_id,
                )

            self._commissions.create(
                id=self._new_id(),
                booking_id=booking_row.id,
                trip_id=trip.id,
                driver_id=trip.driver_id,
                rate_basis_points=split.rate_basis_points,
                gross_minor=split.gross.amount_minor,
                platform_minor=split.platform.amount_minor,
                driver_minor=split.driver.amount_minor,
                currency=split.gross.currency,
            )
            self._wallets.record_trip_settlement(
                wallet=wallet,
                platform_minor=split.platform.amount_minor,
                driver_minor=split.driver.amount_minor,
                # Section 89: fares are collected in cash at the vehicle, so the
                # driver holds the money and owes VELRO its share. Reading the
                # method per booking rather than assuming it leaves room for the
                # payment types the schema already allows.
                cash=booking_row.payment_method == PaymentMethod.CASH.value,
                booking_id=booking_row.id,
                trip_id=trip.id,
            )
            total_driver = total_driver + split.driver
            total_platform = total_platform + split.platform

        self._audit.write(
            "trip.settled",
            actor_id=cmd.actor_id,
            actor_role=cmd.actor_role,
            entity_type="trip",
            entity_id=trip.id,
            after={
                "driver_minor": total_driver.amount_minor,
                "platform_minor": total_platform.amount_minor,
                "currency": total_driver.currency,
                "rate_basis_points": rate,
            },
            request_id=cmd.request_id,
        )
        return total_driver, total_platform


@dataclass(frozen=True, slots=True)
class VerifyPassengerCommand:
    trip_id: str
    presented_code: str
    driver_user_id: str
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class VerifyPassengerResult:
    booking_id: str
    number: str
    passenger_name: str | None
    seat_numbers: list[int]
    status: BookingStatus


class VerifyPassenger:
    """The driver confirms this person belongs in this vehicle.

    Section 25: on a shared ride several strangers board at the same station,
    and putting the wrong person in a seat someone paid for is the failure this
    prevents.
    """

    def __init__(self, *, trips, bookings, drivers, seats, users, audit, clock: Clock) -> None:
        self._trips = trips
        self._bookings = bookings
        self._drivers = drivers
        self._seats = seats
        self._users = users
        self._audit = audit
        self._clock = clock

    def execute(self, cmd: VerifyPassengerCommand) -> VerifyPassengerResult:
        now = self._clock.now()
        trip_row = self._trips.get(cmd.trip_id)

        driver = self._drivers.find_by_user(cmd.driver_user_id)
        if driver is None or trip_row.driver_id != driver.id:
            raise PermissionError(
                error_codes.PERMISSION_DENIED, trip_id=cmd.trip_id, actor_id=cmd.driver_user_id
            )

        row = self._bookings.find_by_verification_code(cmd.trip_id, cmd.presented_code)
        if row is None:
            # Deliberately the same error whether the code is wrong or belongs
            # to another trip: a driver probing codes learns nothing either way.
            raise ConflictError(
                error_codes.BOOKING_VERIFICATION_FAILED, trip_id=cmd.trip_id
            )

        booking = _to_booking(row)
        booking.verify(cmd.presented_code, at=now)

        row.status = booking.status.value
        row.boarded_at = booking.boarded_at
        self._bookings.save(row)
        self._seats.occupy_for_booking(row.id)

        passenger = self._users.find(row.passenger_id)

        self._audit.write(
            "booking.passenger_verified",
            actor_id=cmd.driver_user_id,
            actor_role=ActorRole.DRIVER,
            entity_type="booking",
            entity_id=row.id,
            after={"status": booking.status.value, "trip_id": cmd.trip_id},
            request_id=cmd.request_id,
        )
        return VerifyPassengerResult(
            booking_id=row.id,
            number=row.number,
            passenger_name=passenger.full_name if passenger else None,
            seat_numbers=[s.seat_number for s in self._bookings.seats_of(row.id)],
            status=booking.status,
        )


# The three ways a trip ends without anybody travelling.
_CALLED_OFF = frozenset(
    {TripStatus.CANCELLED, TripStatus.EXPIRED, TripStatus.NO_DRIVER_AVAILABLE}
)


def _tell(notifier, **kwargs) -> None:
    """Best effort, always.

    A notification that cannot be delivered must never roll back the thing it
    was announcing: the trip really is cancelled whether or not the message
    reaches the phone, and the row in the inbox is the record.
    """
    if notifier is None:
        return
    try:
        notifier.notify(**kwargs)
    except Exception:
        log.warning("notify.failed", message_key=kwargs.get("message_key"))


def cascade_bookings(
    bookings, trip_status: TripStatus, now: datetime, *, trip_id: str | None = None
) -> int:
    """Move a trip's bookings to the status its own status implies.

    Bookings already cancelled or marked no-show are left alone: a trip
    departing does not un-cancel someone who withdrew.
    """
    target = TRIP_TO_BOOKING_STATUS.get(trip_status)
    if target is None:
        return 0

    advanced = 0
    for row in bookings.active_for_trip(trip_id) if trip_id else []:
        advanced += _advance_one(bookings, row, target, now)
    return advanced


def _advance_one(bookings, row, target: BookingStatus, now: datetime) -> int:
    booking = _to_booking(row)
    before = booking.status
    booking.follow_trip(target, at=now)
    if booking.status is before:
        return 0
    row.status = booking.status.value
    row.confirmed_at = booking.confirmed_at
    row.boarded_at = booking.boarded_at
    row.completed_at = booking.completed_at
    bookings.save(row)
    return 1


# -- mapping helpers -----------------------------------------------------

def _to_trip(row, seat_rows) -> Trip:
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
        started_at=row.started_at,
        completed_at=row.completed_at,
        cancelled_at=row.cancelled_at,
        seats=[
            TripSeat(
                id=s.id, trip_id=s.trip_id, seat_number=s.seat_number,
                status=s.status, booking_id=s.booking_id, version=s.version,
            )
            for s in seat_rows
        ],
    )


def _to_booking(row) -> Booking:
    return Booking(
        id=row.id,
        number=row.number,
        trip_id=row.trip_id,
        passenger_id=row.passenger_id,
        ride_kind=RideKind(row.ride_kind),
        seat_count=row.seat_count,
        seat_numbers=[],
        pickup_sequence=row.pickup_sequence,
        dropoff_sequence=row.dropoff_sequence,
        pickup_station_id=row.pickup_station_id,
        dropoff_destination_id=row.dropoff_destination_id,
        fare_total=Money(row.fare_total_minor, row.fare_total_currency),
        fare_breakdown=tuple(row.fare_breakdown or ()),
        status=BookingStatus(row.status),
        verification_code=row.verification_code,
        payment_method=PaymentMethod(row.payment_method),
        confirmed_at=row.confirmed_at,
        boarded_at=row.boarded_at,
        completed_at=row.completed_at,
        cancelled_at=row.cancelled_at,
    )
