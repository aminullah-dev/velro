"""Bookings.

A booking is a passenger's claim on specific seats of a specific trip between
two specific stops. It carries its own business number, its own verification
code, and the fare quote as it stood when the booking was made.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass, field
from datetime import datetime

from domain.enums import BookingStatus, PaymentMethod, RideKind
from domain.fare import FareQuote
from domain.lifecycles import BOOKING_LIFECYCLE
from shared import error_codes
from shared.errors import ConflictError, ValidationError
from shared.money import Money

# Statuses from which a passenger may still cancel. Once aboard, a cancellation
# is a trip incident, not a booking change.
CANCELLABLE_STATUSES: frozenset[BookingStatus] = frozenset(
    {
        BookingStatus.PENDING,
        BookingStatus.CONFIRMED,
        BookingStatus.DRIVER_ASSIGNED,
        BookingStatus.READY,
    }
)


@dataclass(slots=True)
class Booking:
    id: str
    number: str                       # BKG-2026-000001
    trip_id: str
    passenger_id: str
    ride_kind: RideKind
    seat_count: int
    seat_numbers: list[int]
    pickup_sequence: int
    dropoff_sequence: int
    pickup_station_id: str
    dropoff_destination_id: str
    fare_total: Money
    fare_breakdown: tuple[dict[str, object], ...]
    status: BookingStatus = BookingStatus.PENDING
    verification_code: str = ""
    payment_method: PaymentMethod = PaymentMethod.CASH
    passenger_note: str | None = None
    confirmed_at: datetime | None = None
    boarded_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancelled_by_role: str | None = None
    cancellation_reason_code: str | None = None
    version: int = 0
    seat_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.status, BookingStatus):
            self.status = BookingStatus(self.status)
        if not isinstance(self.ride_kind, RideKind):
            self.ride_kind = RideKind(self.ride_kind)
        if not isinstance(self.payment_method, PaymentMethod):
            self.payment_method = PaymentMethod(self.payment_method)
        if self.seat_count <= 0:
            raise ValidationError(
                error_codes.BOOKING_SEAT_COUNT_INVALID, seat_count=self.seat_count
            )
        if self.pickup_sequence >= self.dropoff_sequence:
            raise ValidationError(
                error_codes.BOOKING_STOPS_OUT_OF_ORDER,
                pickup_sequence=self.pickup_sequence,
                dropoff_sequence=self.dropoff_sequence,
            )
        if self.fare_total.is_negative:
            raise ValidationError(
                error_codes.FARE_NEGATIVE, amount_minor=self.fare_total.amount_minor
            )

    # -- construction -----------------------------------------------------

    @classmethod
    def from_quote(
        cls,
        *,
        id: str,
        number: str,
        trip_id: str,
        passenger_id: str,
        quote: FareQuote,
        seat_ids: list[str],
        seat_numbers: list[int],
        pickup_station_id: str,
        dropoff_destination_id: str,
        verification_code: str,
        payment_method: PaymentMethod = PaymentMethod.CASH,
        passenger_note: str | None = None,
    ) -> Booking:
        """The fare is frozen onto the booking here, not looked up again later."""
        if len(seat_ids) != quote.seat_count or len(seat_numbers) != quote.seat_count:
            raise ConflictError(
                error_codes.TRIP_SEATS_UNAVAILABLE,
                trip_id=trip_id,
                requested=quote.seat_count,
                allocated=len(seat_ids),
            )
        return cls(
            id=id,
            number=number,
            trip_id=trip_id,
            passenger_id=passenger_id,
            ride_kind=quote.ride_kind,
            seat_count=quote.seat_count,
            seat_numbers=sorted(seat_numbers),
            seat_ids=list(seat_ids),
            pickup_sequence=quote.from_sequence,
            dropoff_sequence=quote.to_sequence,
            pickup_station_id=pickup_station_id,
            dropoff_destination_id=dropoff_destination_id,
            fare_total=quote.total(),
            fare_breakdown=tuple(
                {
                    "key": c.key,
                    "amount_minor": c.amount.amount_minor,
                    "currency": c.amount.currency,
                    "quantity": c.quantity,
                }
                for c in quote.components
            ),
            verification_code=verification_code,
            payment_method=payment_method,
            passenger_note=passenger_note,
        )

    # -- lifecycle --------------------------------------------------------

    def transition_to(self, target: BookingStatus, *, at: datetime) -> None:
        BOOKING_LIFECYCLE.check(self.status, target, booking_id=self.id)
        self.status = target
        if target is BookingStatus.CONFIRMED:
            self.confirmed_at = at
        elif target is BookingStatus.ONBOARD:
            self.boarded_at = at
        elif target is BookingStatus.COMPLETED:
            self.completed_at = at
        elif target in (BookingStatus.CANCELLED, BookingStatus.NO_SHOW):
            self.cancelled_at = at

    def follow_trip(self, target: BookingStatus, *, at: datetime) -> None:
        """Advance alongside the trip, but never resurrect a terminal booking.

        Walks the declared path rather than requiring a single hop: if a
        cascade was missed earlier, this catches the booking up instead of
        leaving a passenger looking at a stale status.
        """
        if BOOKING_LIFECYCLE.is_terminal(self.status):
            return
        route = BOOKING_LIFECYCLE.path(self.status, target)
        if route is None:
            return
        for step in route:
            # Never take a cancellation path to reach a forward state.
            if BOOKING_LIFECYCLE.is_terminal(step) and step is not target:
                return
            self.transition_to(step, at=at)

    def cancel(self, *, by_role: str, reason_code: str, at: datetime) -> None:
        if self.status not in CANCELLABLE_STATUSES:
            raise ConflictError(
                error_codes.BOOKING_NOT_CANCELLABLE,
                booking_id=self.id,
                status=str(self.status),
            )
        self.transition_to(BookingStatus.CANCELLED, at=at)
        self.cancelled_by_role = by_role
        self.cancellation_reason_code = reason_code

    # -- boarding ---------------------------------------------------------

    def verify(self, presented_code: str, *, at: datetime) -> None:
        """A driver confirms this passenger belongs on this vehicle.

        Compared in constant time: the code is short, so a timing oracle would
        genuinely help someone guess it.
        """
        if not hmac.compare_digest(
            presented_code.strip().upper(), self.verification_code.upper()
        ):
            raise ConflictError(
                error_codes.BOOKING_VERIFICATION_FAILED, booking_id=self.id
            )
        self.transition_to(BookingStatus.ONBOARD, at=at)

    @property
    def is_active(self) -> bool:
        return not BOOKING_LIFECYCLE.is_terminal(self.status)
