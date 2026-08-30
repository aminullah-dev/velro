from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from domain.enums import (
    BookingStatus,
    FareOfferStatus,
    PaymentMethod,
    RideKind,
    RideRequestStatus,
    SeatStatus,
    TripStatus,
)
from infrastructure.db.base import Auditable, Base, enum_check


class TripRow(Auditable, Base):
    __tablename__ = "trips"

    number: Mapped[str] = mapped_column(String(24), nullable=False)   # VLR-2026-000001
    route_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("routes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    schedule_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("route_schedules.id", ondelete="RESTRICT"), index=True
    )
    ride_kind: Mapped[str] = mapped_column(String(12), nullable=False)
    seat_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    scheduled_departure_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    origin_station_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    destination_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("destinations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    driver_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("drivers.id", ondelete="RESTRICT"), index=True
    )
    vehicle_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("vehicles.id", ondelete="RESTRICT"), index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason_code: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        UniqueConstraint("number", name="uq_trips_number"),
        # The search query: available trips on a route around a departure time.
        Index("ix_trips_route_id_scheduled_departure_at", "route_id", "scheduled_departure_at"),
        Index("ix_trips_status_scheduled_departure_at", "status", "scheduled_departure_at"),
        CheckConstraint("seat_capacity > 0", name="ck_trips_capacity_positive"),
        enum_check("status", TripStatus, name="trips_status"),
        enum_check("ride_kind", RideKind, name="trips_ride_kind"),
    )


class TripStopRow(Auditable, Base):
    __tablename__ = "trip_stops"

    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    station_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stations.id", ondelete="RESTRICT"), index=True
    )
    destination_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("destinations.id", ondelete="RESTRICT"), index=True
    )
    planned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("trip_id", "sequence", name="uq_trip_stops_trip_id_sequence"),
        CheckConstraint(
            "(station_id IS NULL) <> (destination_id IS NULL)",
            name="ck_trip_stops_exactly_one_place",
        ),
    )


class TripSeatRow(Auditable, Base):
    """Seats are rows, not a counter.

    Capacity therefore cannot be exceeded by construction, and the uniqueness of
    (trip_id, seat_number) means the same seat cannot exist twice however the
    application misbehaves.
    """

    __tablename__ = "trip_seats"

    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    seat_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), default=SeatStatus.AVAILABLE.value, nullable=False
    )
    booking_id: Mapped[str | None] = mapped_column(String(36), index=True)

    __table_args__ = (
        UniqueConstraint("trip_id", "seat_number", name="uq_trip_seats_trip_id_seat_number"),
        # The hot path: "give me N available seats on this trip", locked.
        Index("ix_trip_seats_trip_id_status_seat_number", "trip_id", "status", "seat_number"),
        CheckConstraint("seat_number > 0", name="ck_trip_seats_seat_number_positive"),
        enum_check("status", SeatStatus, name="trip_seats_status"),
    )


class BookingRow(Auditable, Base):
    __tablename__ = "bookings"

    number: Mapped[str] = mapped_column(String(24), nullable=False)   # BKG-2026-000001
    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    passenger_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ride_kind: Mapped[str] = mapped_column(String(12), nullable=False)
    seat_count: Mapped[int] = mapped_column(Integer, nullable=False)
    pickup_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    dropoff_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    pickup_station_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    dropoff_destination_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("destinations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # The fare as quoted at booking time. Never recomputed: changing a route
    # price tomorrow must not change what this passenger was charged today.
    fare_total_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    fare_total_currency: Mapped[str] = mapped_column(String(3), default="AFN", nullable=False)
    fare_breakdown: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    fare_rule_id: Mapped[str | None] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    verification_code: Mapped[str] = mapped_column(String(12), nullable=False)
    payment_method: Mapped[str] = mapped_column(
        String(20), default=PaymentMethod.CASH.value, nullable=False
    )
    passenger_note: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    boarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_role: Mapped[str | None] = mapped_column(String(20))
    cancellation_reason_code: Mapped[str | None] = mapped_column(String(40))

    __table_args__ = (
        UniqueConstraint("number", name="uq_bookings_number"),
        Index("ix_bookings_passenger_id_created_at", "passenger_id", "created_at"),
        Index("ix_bookings_trip_id_status", "trip_id", "status"),
        CheckConstraint("seat_count > 0", name="ck_bookings_seat_count_positive"),
        CheckConstraint("fare_total_minor >= 0", name="ck_bookings_fare_non_negative"),
        CheckConstraint(
            "pickup_sequence < dropoff_sequence", name="ck_bookings_stop_order"
        ),
        enum_check("status", BookingStatus, name="bookings_status"),
        enum_check("ride_kind", RideKind, name="bookings_ride_kind"),
        enum_check("payment_method", PaymentMethod, name="bookings_payment_method"),
    )


class BookingSeatRow(Auditable, Base):
    """The correctness backstop for the whole platform.

    UNIQUE(trip_seat_id) makes it structurally impossible for two bookings to
    hold the same seat. The row lock in the repository provides liveness; this
    constraint provides the guarantee, and it holds even if that query is later
    changed carelessly.
    """

    __tablename__ = "booking_seats"

    booking_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    trip_seat_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trip_seats.id", ondelete="RESTRICT"), nullable=False
    )
    seat_number: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("trip_seat_id", name="uq_booking_seats_trip_seat_id"),
    )


class RideRequestRow(Auditable, Base):
    """A passenger asking to be driven, at a price they proposed.

    Section 89: VELRO does not price a journey. Nobody knows the distance
    between two villages in Ghorband, or which stretch of road is asphalt and
    which is dirt, so the fare is agreed between the passenger and a driver --
    which is how it is already agreed at the station.
    """

    __tablename__ = "ride_requests"

    passenger_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    origin_station_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    destination_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("destinations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    route_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("routes.id", ondelete="RESTRICT"), index=True
    )
    trip_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="RESTRICT"), index=True
    )
    passenger_count: Mapped[int] = mapped_column(Integer, nullable=False)
    vehicle_type_code: Mapped[str | None] = mapped_column(String(24))
    requested_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # When they want to come back, if they said. Null is "one way", which
    # is most of them.
    return_for: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    # What the passenger proposed. Not a quote from the platform -- there is no
    # platform quote.
    # The outbound leg for a round trip, the whole fare for a one-way one.
    offered_fare_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    # The return leg. Null is "no return", never "a return costing nothing".
    return_fare_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    offered_fare_currency: Mapped[str] = mapped_column(
        String(3), default="AFN", nullable=False
    )
    # What was finally settled on, which is the accepted offer, not the asking
    # price. Null until a driver is agreed.
    agreed_fare_minor: Mapped[int | None] = mapped_column(Integer)
    accepted_offer_id: Mapped[str | None] = mapped_column(String(36), index=True)
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_ride_requests_status_expires_at", "status", "expires_at"),
        # The driver's board: open requests from a station, soonest first.
        Index("ix_ride_requests_origin_status", "origin_station_id", "status"),
        CheckConstraint("passenger_count > 0", name="ck_ride_requests_passenger_count_positive"),
        CheckConstraint(
            "offered_fare_minor > 0", name="ck_ride_requests_offer_positive"
        ),
        CheckConstraint(
            "return_fare_minor IS NULL OR return_fare_minor > 0",
            name="ck_ride_requests_return_fare_positive",
        ),
        enum_check("status", RideRequestStatus, name="ride_requests_status"),
    )


class FareOfferRow(Auditable, Base):
    """One driver's price for one request.

    A row per driver, not per exchange: changing your mind is withdrawing and
    offering again, so the passenger sees one number from each driver rather
    than a negotiation history to read through at the roadside.
    """

    __tablename__ = "fare_offers"

    ride_request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ride_requests.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    driver_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drivers.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    vehicle_id: Mapped[str | None] = mapped_column(String(36))
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    return_amount_minor: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_currency: Mapped[str] = mapped_column(String(3), default="AFN", nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), default=FareOfferStatus.OFFERED.value, nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # One live offer per driver per request. A driver who offers twice is
        # either double-tapping or gaming the list; both are the same mistake.
        Index(
            "uq_fare_offers_request_driver_open",
            "ride_request_id", "driver_id",
            unique=True,
            postgresql_where=text("status = 'OFFERED'"),
        ),
        CheckConstraint("amount_minor > 0", name="ck_fare_offers_amount_positive"),
        CheckConstraint(
            "return_amount_minor IS NULL OR return_amount_minor > 0",
            name="ck_fare_offers_return_amount_positive",
        ),
        enum_check("status", FareOfferStatus, name="fare_offers_status"),
    )


class DispatchOfferRow(Auditable, Base):
    """One offer of one trip to one driver. The history is the dispatch audit."""

    __tablename__ = "dispatch_offers"

    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    driver_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drivers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    offered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response: Mapped[str | None] = mapped_column(String(16))   # ACCEPTED / DECLINED / TIMEOUT
    decline_reason: Mapped[str | None] = mapped_column(String(40))
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "trip_id", "driver_id", "offered_at",
            name="uq_dispatch_offers_trip_id_driver_id_offered_at",
        ),
        Index("ix_dispatch_offers_driver_id_expires_at", "driver_id", "expires_at"),
    )
