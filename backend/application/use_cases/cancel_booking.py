"""Cancelling a booking.

Cancelling frees the seats, which is the point: a seat held by a cancelled
booking is a seat nobody can buy and a vehicle that leaves emptier than it
needed to. Freeing them and writing the cancellation record happen in the same
transaction as the status change.

The policy -- who may cancel, until when, and at what fee -- is configuration,
not code (section 43).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from domain.enums import ActorRole, BookingStatus, TripStatus
from domain.lifecycles import BOOKING_LIFECYCLE
from shared import error_codes
from shared.errors import ConflictError, NotFoundError, PermissionError
from shared.money import Money

# Reason codes are a closed set so that reporting can group them; the sentence
# shown to a person comes from a translation of the code.
REASON_PASSENGER = "PASSENGER_CANCELLED"
REASON_DRIVER = "DRIVER_CANCELLED"
REASON_NO_DRIVER = "NO_DRIVER_AVAILABLE"
REASON_VEHICLE = "VEHICLE_PROBLEM"
REASON_WEATHER = "WEATHER"
REASON_ADMIN = "ADMIN_CANCELLED"
REASON_OTHER = "OTHER"

VALID_REASONS = frozenset(
    {REASON_PASSENGER, REASON_DRIVER, REASON_NO_DRIVER, REASON_VEHICLE,
     REASON_WEATHER, REASON_ADMIN, REASON_OTHER}
)


@dataclass(frozen=True, slots=True)
class CancelBookingCommand:
    booking_id: str
    actor_id: str
    actor_role: ActorRole
    reason_code: str = REASON_PASSENGER
    note: str | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class CancelBookingResult:
    booking_id: str
    status: BookingStatus
    seats_released: int
    fee: Money


class CancelBooking:
    def __init__(
        self,
        *,
        bookings,
        trips,
        seats,
        cancellations,
        settings,
        audit,
        clock,
        new_id,
        drivers,
    ) -> None:
        self._bookings = bookings
        self._trips = trips
        self._seats = seats
        self._cancellations = cancellations
        self._settings = settings
        self._audit = audit
        self._clock = clock
        self._new_id = new_id
        self._drivers = drivers

    def execute(self, cmd: CancelBookingCommand) -> CancelBookingResult:
        now = self._clock.now()
        if cmd.reason_code not in VALID_REASONS:
            raise ConflictError(
                error_codes.VALIDATION_FAILED, field="reason_code", value=cmd.reason_code
            )

        # Locked. A cancellation writes a financial record -- the fee, even
        # when it is zero -- and releases seats, and two taps on a slow
        # connection are two requests. On an unlocked row both read
        # CONFIRMED, both cancel, and the booking ends up with two
        # cancellation records for one journey. The second now waits, reads
        # CANCELLED, and is refused as already cancelled.
        row = self._bookings.lock(cmd.booking_id)
        if row is None:
            raise NotFoundError(self._bookings.not_found_code, id=cmd.booking_id)

        # A passenger may cancel only their own booking. Staff may cancel any,
        # and the audit entry records which happened.
        if cmd.actor_role is ActorRole.PASSENGER and row.passenger_id != cmd.actor_id:
            raise PermissionError(
                error_codes.PERMISSION_DENIED, booking_id=cmd.booking_id, actor_id=cmd.actor_id
            )

        if BOOKING_LIFECYCLE.is_terminal(BookingStatus(row.status)):
            raise ConflictError(
                error_codes.BOOKING_ALREADY_CANCELLED,
                booking_id=row.id,
                status=row.status,
            )

        from application.use_cases.trip_lifecycle import _to_booking

        booking = _to_booking(row)
        trip = self._trips.get(row.trip_id)

        # A driver may cancel only a booking on their own trip -- unless it is
        # their own booking, ridden as a passenger: a person can hold both
        # roles on the same account, and this endpoint's own actor.role is a
        # single derived label (deps.Actor.role picks DRIVER over PASSENGER
        # whenever both apply), so a driver cancelling a seat they themselves
        # booked must not be caught by a check meant for someone else's trip.
        # Staff may cancel any booking, and the audit entry records which
        # happened -- staff-wide cancel authority is existing, intentional
        # behaviour and is left alone here.
        if cmd.actor_role is ActorRole.DRIVER and row.passenger_id != cmd.actor_id:
            driver = self._drivers.find_by_user(cmd.actor_id)
            if driver is None or trip is None or trip.driver_id != driver.id:
                raise PermissionError(
                    error_codes.PERMISSION_DENIED,
                    booking_id=cmd.booking_id,
                    actor_id=cmd.actor_id,
                )

        fee = self._cancellation_fee(booking, trip, now, cmd.actor_role)

        booking.cancel(by_role=cmd.actor_role.value, reason_code=cmd.reason_code, at=now)
        row.status = booking.status.value
        row.cancelled_at = booking.cancelled_at
        row.cancelled_by_role = booking.cancelled_by_role
        row.cancellation_reason_code = booking.cancellation_reason_code
        self._bookings.save(row)

        released = self._seats.release_for_booking(row.id)

        self._cancellations.create(
            id=self._new_id(),
            trip_id=row.trip_id,
            booking_id=row.id,
            cancelled_by_user_id=cmd.actor_id,
            cancelled_by_role=cmd.actor_role.value,
            reason_code=cmd.reason_code,
            note=cmd.note,
            fee_minor=fee.amount_minor,
            fee_currency=fee.currency,
        )
        self._audit.write(
            "booking.cancelled",
            actor_id=cmd.actor_id,
            actor_role=cmd.actor_role,
            entity_type="booking",
            entity_id=row.id,
            before={"status": BookingStatus.CONFIRMED.value},
            after={
                "status": booking.status.value,
                "reason_code": cmd.reason_code,
                "seats_released": released,
                "fee_minor": fee.amount_minor,
            },
            request_id=cmd.request_id,
        )
        return CancelBookingResult(
            booking_id=row.id,
            status=booking.status,
            seats_released=released,
            fee=fee,
        )

    def _cancellation_fee(self, booking, trip, now, actor_role: ActorRole) -> Money:
        """Free outside the configured window; free always when it was not the
        passenger's doing. Charging someone for a driver's cancellation is the
        kind of detail that loses a market."""
        currency = booking.fare_total.currency
        if actor_role is not ActorRole.PASSENGER:
            return Money.zero(currency)

        window = self._settings.get_int("booking.cancellation_window_minutes", 15)
        if trip.status == TripStatus.SCHEDULED.value:
            return Money.zero(currency)
        if now + timedelta(minutes=window) <= trip.scheduled_departure_at:
            return Money.zero(currency)

        late_bp = self._settings.get_int("booking.late_cancellation_basis_points", 0)
        return booking.fare_total.percentage(late_bp)
