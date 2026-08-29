from __future__ import annotations

from datetime import date, time

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from domain.enums import OriginScope, RideKind, RouteStatus, RouteType
from infrastructure.db.base import Auditable, Base, enum_check


class VehicleTypeRow(Auditable, Base):
    """Sedan, SUV, Van, Hiace, Bus, Other -- a row, so an operator can add one
    without a deploy (section 105)."""

    __tablename__ = "vehicle_types"

    code: Mapped[str] = mapped_column(String(24), nullable=False)
    name_key: Mapped[str] = mapped_column(String(80), nullable=False)
    default_seat_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("code", name="uq_vehicle_types_code"),
        CheckConstraint("default_seat_capacity > 0", name="ck_vehicle_types_capacity_positive"),
    )


class RouteTemplateRow(Auditable, Base):
    """The rule that generates routes. Section 12: no route is wired up per village."""

    __tablename__ = "route_templates"

    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    origin_scope: Mapped[str] = mapped_column(String(12), nullable=False)
    origin_ref_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    destination_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("destinations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    route_type: Mapped[str] = mapped_column(String(24), nullable=False)
    vehicle_type_code: Mapped[str] = mapped_column(String(24), nullable=False)
    default_seat_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    # Ordered destination ids the generated route passes through, between the
    # origin station and the final destination.
    intermediate_destination_ids: Mapped[list[str] | None] = mapped_column(JSON)
    base_fare_minor: Mapped[int | None] = mapped_column(Integer)
    base_fare_currency: Mapped[str | None] = mapped_column(String(3))
    distance_m: Mapped[int | None] = mapped_column(Integer)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(12), default=RouteStatus.ACTIVE.value, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_route_templates_code"),
        enum_check("origin_scope", OriginScope, name="route_templates_origin_scope"),
        enum_check("route_type", RouteType, name="route_templates_route_type"),
        enum_check("status", RouteStatus, name="route_templates_status"),
        CheckConstraint(
            "default_seat_capacity > 0", name="ck_route_templates_capacity_positive"
        ),
        CheckConstraint(
            "base_fare_minor IS NULL OR base_fare_minor >= 0",
            name="ck_route_templates_fare_non_negative",
        ),
    )


class RouteRow(Auditable, Base):
    __tablename__ = "routes"

    code: Mapped[str] = mapped_column(String(48), nullable=False)
    route_type: Mapped[str] = mapped_column(String(24), nullable=False)
    origin_station_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("stations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    destination_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("destinations.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    template_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("route_templates.id", ondelete="RESTRICT"), index=True
    )
    distance_m: Mapped[int | None] = mapped_column(Integer)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(12), default=RouteStatus.DRAFT.value, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("code", name="uq_routes_code"),
        # One materialised route per (origin, destination, template). Regenerating
        # a template must update rather than duplicate.
        Index("ix_routes_origin_station_id_destination_id", "origin_station_id", "destination_id"),
        enum_check("route_type", RouteType, name="routes_route_type"),
        enum_check("status", RouteStatus, name="routes_status"),
        CheckConstraint(
            "distance_m IS NULL OR distance_m >= 0", name="ck_routes_distance_non_negative"
        ),
    )


class RouteStopRow(Auditable, Base):
    __tablename__ = "route_stops"

    route_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("routes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    station_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stations.id", ondelete="RESTRICT"), index=True
    )
    destination_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("destinations.id", ondelete="RESTRICT"), index=True
    )
    is_pickup: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_dropoff: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        # Partial: a soft-deleted stop must not keep occupying its sequence.
        # Regenerating a route rebuilds its stops at the same sequences, and a
        # plain constraint counts the dead rows and blocks the insert.
        Index(
            "uq_route_stops_route_id_sequence",
            "route_id", "sequence",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        CheckConstraint(
            "(station_id IS NULL) <> (destination_id IS NULL)",
            name="ck_route_stops_exactly_one_place",
        ),
        CheckConstraint("sequence >= 0", name="ck_route_stops_sequence_non_negative"),
    )


class RouteScheduleRow(Auditable, Base):
    """A standing departure. 'Saturday 07:00' rather than a specific date."""

    __tablename__ = "route_schedules"

    route_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("routes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Seven characters, one per weekday starting Saturday (the Afghan week):
    # 'YYYYYYN' means Saturday-Thursday but not Friday.
    days_of_week: Mapped[str] = mapped_column(String(7), nullable=False)
    departure_time: Mapped[time] = mapped_column(Time, nullable=False)
    vehicle_type_code: Mapped[str] = mapped_column(String(24), nullable=False)
    seat_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    ride_kind: Mapped[str] = mapped_column(
        String(12), default=RideKind.SHARED.value, nullable=False
    )
    active_from: Mapped[date] = mapped_column(Date, nullable=False)
    active_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        # Explicit short name: the generated one exceeds PostgreSQL's 63-char
        # identifier limit.
        UniqueConstraint(
            "route_id", "departure_time", "vehicle_type_code", "active_from",
            name="uq_route_schedules_departure",
        ),
        CheckConstraint("seat_capacity > 0", name="ck_route_schedules_capacity_positive"),
        CheckConstraint("length(days_of_week) = 7", name="ck_route_schedules_days_length"),
        enum_check("ride_kind", RideKind, name="route_schedules_ride_kind"),
    )


class FareRuleRow(Auditable, Base):
    """A price for a leg. Superseding a price closes the old row and inserts a
    new one, so a historical booking can always be explained."""

    __tablename__ = "fare_rules"

    route_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("routes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ride_kind: Mapped[str] = mapped_column(String(12), nullable=False)
    vehicle_type_code: Mapped[str | None] = mapped_column(String(24))
    from_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    to_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_currency: Mapped[str] = mapped_column(String(3), default="AFN", nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(
            "ix_fare_rules_route_id_ride_kind_valid_from",
            "route_id", "ride_kind", "valid_from",
        ),
        CheckConstraint("amount_minor >= 0", name="ck_fare_rules_amount_non_negative"),
        CheckConstraint("from_sequence < to_sequence", name="ck_fare_rules_sequence_order"),
        CheckConstraint(
            "valid_to IS NULL OR valid_to >= valid_from", name="ck_fare_rules_validity_order"
        ),
        enum_check("ride_kind", RideKind, name="fare_rules_ride_kind"),
    )
