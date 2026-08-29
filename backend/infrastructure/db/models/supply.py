from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from domain.enums import (
    DocumentStatus,
    DriverApprovalStatus,
    DriverAvailability,
    VehicleStatus,
)
from infrastructure.db.base import Auditable, Base, enum_check


class DriverRow(Auditable, Base):
    __tablename__ = "drivers"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    approval_status: Mapped[str] = mapped_column(
        String(16), default=DriverApprovalStatus.PENDING.value, nullable=False
    )
    availability: Mapped[str] = mapped_column(
        String(12), default=DriverAvailability.OFFLINE.value, nullable=False
    )
    # Sum and count rather than a stored average: an average recomputed from an
    # average drifts, and this way a rating can be corrected exactly.
    rating_sum: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_trips: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    home_district_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("districts.id", ondelete="RESTRICT"), index=True
    )
    home_station_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stations.id", ondelete="RESTRICT"), index=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(String(36))
    suspended_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("user_id", name="uq_drivers_user_id"),
        # The dispatch query: approved drivers who are online right now.
        Index("ix_drivers_approval_status_availability", "approval_status", "availability"),
        CheckConstraint("rating_count >= 0", name="ck_drivers_rating_count_non_negative"),
        CheckConstraint(
            "rating_sum >= 0 AND rating_sum <= rating_count * 5",
            name="ck_drivers_rating_sum_in_range",
        ),
        enum_check("approval_status", DriverApprovalStatus, name="drivers_approval_status"),
        enum_check("availability", DriverAvailability, name="drivers_availability"),
    )


class DriverDocumentRow(Auditable, Base):
    __tablename__ = "driver_documents"

    driver_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drivers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    document_type_code: Mapped[str] = mapped_column(String(40), nullable=False)
    file_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), default=DocumentStatus.PENDING.value, nullable=False
    )
    expires_on: Mapped[date | None] = mapped_column(Date)
    verified_by: Mapped[str | None] = mapped_column(String(36))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(
            "ix_driver_documents_driver_id_document_type_code",
            "driver_id", "document_type_code",
        ),
        enum_check("status", DocumentStatus, name="driver_documents_status"),
    )


class VehicleDocumentRow(Auditable, Base):
    """جواز سیر and anything else the car itself must carry.

    A separate table from driver_documents rather than a nullable owner column
    on it. The two hang off different aggregates with different lifecycles, and
    a shared table with a discriminator is how a permit for a car the driver no
    longer owns ends up still counting. The validity *rules* are shared in
    domain.documents; only the ownership is separate.
    """

    __tablename__ = "vehicle_documents"

    vehicle_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("vehicles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    document_type_code: Mapped[str] = mapped_column(String(40), nullable=False)
    file_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), default=DocumentStatus.PENDING.value, nullable=False
    )
    expires_on: Mapped[date | None] = mapped_column(Date)
    verified_by: Mapped[str | None] = mapped_column(String(36))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(
            "ix_vehicle_documents_vehicle_id_document_type_code",
            "vehicle_id", "document_type_code",
        ),
        enum_check("status", DocumentStatus, name="vehicle_documents_status"),
    )


class VehicleRow(Auditable, Base):
    __tablename__ = "vehicles"

    driver_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drivers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    vehicle_type_code: Mapped[str] = mapped_column(
        String(24), nullable=False, index=True
    )
    plate_number: Mapped[str] = mapped_column(String(32), nullable=False)
    # The comparison form: upper case, alphanumeric only, Latin digits. Stored
    # separately so the plate keeps whatever the driver actually typed while
    # uniqueness is decided on what it means.
    plate_key: Mapped[str] = mapped_column(String(32), nullable=False)
    seat_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    brand: Mapped[str | None] = mapped_column(String(60))
    model: Mapped[str | None] = mapped_column(String(60))
    year: Mapped[int | None] = mapped_column(Integer)
    colour: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(
        String(12), default=VehicleStatus.PENDING.value, nullable=False
    )

    __table_args__ = (
        # Uniqueness is on the normalised key, not the raw text: "PRW-1234" and
        # "prw 1234" are one vehicle, and two records for one vehicle means two
        # drivers can be dispatched in it.
        UniqueConstraint("plate_key", name="uq_vehicles_plate_key"),
        CheckConstraint("seat_capacity > 0", name="ck_vehicles_capacity_positive"),
        CheckConstraint(
            "year IS NULL OR (year >= 1950 AND year <= 2100)", name="ck_vehicles_year_plausible"
        ),
        enum_check("status", VehicleStatus, name="vehicles_status"),
    )


class DriverLocationRow(Auditable, Base):
    """One current position per driver.

    Deliberately a single hot row rather than a history table: dispatch reads
    this on every match, and a growing trail would make that query slower every
    week. Trip tracking history, when it is needed, is written separately and
    pruned.
    """

    __tablename__ = "driver_locations"

    driver_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drivers.id", ondelete="RESTRICT"), nullable=False
    )
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    heading_degrees: Mapped[int | None] = mapped_column(Integer)
    accuracy_m: Mapped[int | None] = mapped_column(Integer)
    trip_id: Mapped[str | None] = mapped_column(String(36), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("driver_id", name="uq_driver_locations_driver_id"),
        Index("ix_driver_locations_recorded_at", "recorded_at"),
        CheckConstraint(
            "heading_degrees IS NULL OR (heading_degrees >= 0 AND heading_degrees < 360)",
            name="ck_driver_locations_heading_range",
        ),
    )
