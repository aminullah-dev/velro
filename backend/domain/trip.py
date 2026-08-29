"""Trips and seats.

A trip is one vehicle travelling one route at one time. Its seats are *rows*,
not a counter: capacity therefore cannot be exceeded by construction, and the
final seat cannot be sold twice even if two requests arrive in the same
microsecond. The database enforcement that makes this hold under concurrency
lives in the repository; this module holds the rules that must be true
regardless of storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from domain.enums import RideKind, SeatStatus, TripStatus
from domain.lifecycles import BOOKABLE_TRIP_STATUSES, TRIP_LIFECYCLE
from shared import error_codes
from shared.errors import ConflictError, ValidationError


@dataclass(slots=True)
class TripStop:
    id: str
    trip_id: str
    sequence: int
    station_id: str | None = None
    destination_id: str | None = None
    planned_at: datetime | None = None
    arrived_at: datetime | None = None

    @property
    def place_id(self) -> str:
        return self.station_id or self.destination_id  # type: ignore[return-value]


@dataclass(slots=True)
class TripSeat:
    id: str
    trip_id: str
    seat_number: int
    status: SeatStatus = SeatStatus.AVAILABLE
    booking_id: str | None = None
    version: int = 0

    def __post_init__(self) -> None:
        if self.seat_number <= 0:
            raise ValidationError(error_codes.VALIDATION_FAILED, field="seat_number")
        # Coerced here rather than trusted from the caller: a raw status string
        # from storage compares False against a StrEnum member under `is`, and
        # the failure is silent -- every seat reads as unavailable.
        if not isinstance(self.status, SeatStatus):
            self.status = SeatStatus(self.status)

    @property
    def is_available(self) -> bool:
        return self.status is SeatStatus.AVAILABLE and self.booking_id is None

    def reserve(self, booking_id: str) -> None:
        if not self.is_available:
            raise ConflictError(
                error_codes.TRIP_SEATS_UNAVAILABLE,
                trip_id=self.trip_id,
                seat_number=self.seat_number,
                status=str(self.status),
            )
        self.status = SeatStatus.RESERVED
        self.booking_id = booking_id

    def occupy(self) -> None:
        if self.status is not SeatStatus.RESERVED:
            raise ConflictError(
                error_codes.TRIP_SEATS_UNAVAILABLE,
                trip_id=self.trip_id,
                seat_number=self.seat_number,
                status=str(self.status),
            )
        self.status = SeatStatus.OCCUPIED

    def release(self) -> None:
        """Returns a seat to the pool when a booking is cancelled."""
        if self.status is SeatStatus.BLOCKED:
            raise ConflictError(
                error_codes.TRIP_SEATS_UNAVAILABLE,
                trip_id=self.trip_id,
                seat_number=self.seat_number,
                status=str(self.status),
            )
        self.status = SeatStatus.AVAILABLE
        self.booking_id = None

    def block(self) -> None:
        """Taken out of service -- a broken seat, or one held for an operator."""
        if self.booking_id is not None:
            raise ConflictError(
                error_codes.TRIP_SEATS_UNAVAILABLE,
                trip_id=self.trip_id,
                seat_number=self.seat_number,
                reason="seat is booked",
            )
        self.status = SeatStatus.BLOCKED


@dataclass(slots=True)
class Trip:
    id: str
    number: str                       # VLR-2026-000001
    route_id: str
    ride_kind: RideKind
    seat_capacity: int
    scheduled_departure_at: datetime
    status: TripStatus
    origin_station_id: str
    destination_id: str
    driver_id: str | None = None
    vehicle_id: str | None = None
    stops: list[TripStop] = field(default_factory=list)
    seats: list[TripSeat] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancellation_reason_code: str | None = None
    version: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.status, TripStatus):
            self.status = TripStatus(self.status)
        if not isinstance(self.ride_kind, RideKind):
            self.ride_kind = RideKind(self.ride_kind)
        if self.seat_capacity <= 0:
            raise ValidationError(
                error_codes.VEHICLE_CAPACITY_INVALID, capacity=self.seat_capacity
            )
        if self.scheduled_departure_at.tzinfo is None:
            raise ValidationError(error_codes.VALIDATION_FAILED, field="scheduled_departure_at")
        if len(self.seats) > self.seat_capacity:
            raise ConflictError(
                error_codes.TRIP_CAPACITY_EXCEEDED,
                trip_id=self.id,
                capacity=self.seat_capacity,
                seats=len(self.seats),
            )

    # -- seat availability ------------------------------------------------

    @property
    def available_seats(self) -> list[TripSeat]:
        return sorted(
            (s for s in self.seats if s.is_available), key=lambda s: s.seat_number
        )

    @property
    def seats_available(self) -> int:
        return len(self.available_seats)

    @property
    def is_bookable(self) -> bool:
        return self.status in BOOKABLE_TRIP_STATUSES

    def assert_bookable(self, seat_count: int) -> None:
        """Everything that must be true before seats are locked for a booking.

        This is the optimistic pre-check that produces a good error message. It
        is *not* the guarantee -- the guarantee is the row lock and the unique
        constraint in the repository, because two callers can both pass this
        check at the same instant.
        """
        if seat_count <= 0:
            raise ValidationError(
                error_codes.BOOKING_SEAT_COUNT_INVALID, seat_count=seat_count
            )
        if self.status is TripStatus.CANCELLED:
            raise ConflictError(error_codes.TRIP_CANCELLED, trip_id=self.id)
        if not self.is_bookable:
            raise ConflictError(
                error_codes.TRIP_DEPARTED, trip_id=self.id, status=str(self.status)
            )
        if seat_count > self.seats_available:
            raise ConflictError(
                error_codes.TRIP_SEATS_UNAVAILABLE,
                trip_id=self.id,
                requested=seat_count,
                available=self.seats_available,
            )

    # -- lifecycle --------------------------------------------------------

    def transition_to(self, target: TripStatus, *, at: datetime) -> None:
        TRIP_LIFECYCLE.check(self.status, target, trip_id=self.id)
        self.status = target
        if target is TripStatus.IN_TRANSIT:
            self.started_at = at
        elif target is TripStatus.COMPLETED:
            self.completed_at = at
        elif target in (TripStatus.CANCELLED, TripStatus.EXPIRED):
            self.cancelled_at = at

    def assign_driver(self, driver_id: str, vehicle_id: str, *, at: datetime) -> None:
        if self.driver_id is not None and self.status not in (
            TripStatus.SCHEDULED,
            TripStatus.REQUESTED,
        ):
            raise ConflictError(
                error_codes.TRIP_DRIVER_ALREADY_ASSIGNED,
                trip_id=self.id,
                driver_id=self.driver_id,
            )
        self.transition_to(TripStatus.DRIVER_ASSIGNED, at=at)
        self.driver_id = driver_id
        self.vehicle_id = vehicle_id

    def release_driver(self, *, at: datetime) -> None:
        """Return an assigned trip to the dispatch pool without losing its bookings."""
        target = TripStatus.SCHEDULED if self.ride_kind is RideKind.SHARED else TripStatus.REQUESTED
        self.transition_to(target, at=at)
        self.driver_id = None
        self.vehicle_id = None

    def cancel(self, reason_code: str, *, at: datetime) -> None:
        self.transition_to(TripStatus.CANCELLED, at=at)
        self.cancellation_reason_code = reason_code

    def ordered_stops(self) -> list[TripStop]:
        return sorted(self.stops, key=lambda s: s.sequence)
