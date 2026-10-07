from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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

from domain.enums import DestinationKind, GeoStatus, PlaceStatus
from infrastructure.db.base import Auditable, Base, enum_check

# Coordinates are Numeric, never float: a float round-trip moves a station by
# metres, and they are optional everywhere because a passenger with no GPS fix
# must still be able to travel.
_LAT = Numeric(9, 6)
_LON = Numeric(9, 6)


class ProvinceRow(Auditable, Base):
    __tablename__ = "provinces"

    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), default="AF", nullable=False)
    status: Mapped[str] = mapped_column(String(12), default=GeoStatus.ACTIVE.value, nullable=False)

    __table_args__ = (
        UniqueConstraint("code", name="uq_provinces_code"),
        enum_check("status", GeoStatus, name="provinces_status"),
    )


class RegionRow(Auditable, Base):
    __tablename__ = "regions"

    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    province_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("provinces.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(12), default=GeoStatus.ACTIVE.value, nullable=False)

    __table_args__ = (
        UniqueConstraint("code", name="uq_regions_code"),
        enum_check("status", GeoStatus, name="regions_status"),
    )


class DistrictRow(Auditable, Base):
    __tablename__ = "districts"

    code: Mapped[str] = mapped_column(String(20), nullable=False)      # GRB-SYG
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    alternative_name: Mapped[str | None] = mapped_column(String(120))
    province_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("provinces.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    region_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("regions.id", ondelete="RESTRICT"), index=True
    )
    latitude: Mapped[Decimal | None] = mapped_column(_LAT)
    longitude: Mapped[Decimal | None] = mapped_column(_LON)
    status: Mapped[str] = mapped_column(String(12), default=GeoStatus.ACTIVE.value, nullable=False)

    __table_args__ = (
        UniqueConstraint("code", name="uq_districts_code"),
        enum_check("status", GeoStatus, name="districts_status"),
    )


class VillageRow(Auditable, Base):
    __tablename__ = "villages"

    code: Mapped[str] = mapped_column(String(24), nullable=False)      # GRB-SYG-001
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    # The normalised comparison form, maintained by the importer. Indexed so
    # duplicate detection over tens of thousands of rows stays a lookup rather
    # than a scan.
    name_key: Mapped[str] = mapped_column(String(160), nullable=False)
    district_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("districts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    latitude: Mapped[Decimal | None] = mapped_column(_LAT)
    longitude: Mapped[Decimal | None] = mapped_column(_LON)
    status: Mapped[str] = mapped_column(String(12), default=GeoStatus.ACTIVE.value, nullable=False)
    source_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("code", name="uq_villages_code"),
        # Deliberately NOT unique on (district_id, name_key): section 7 requires
        # that two genuinely different places sharing a name remain two records.
        Index("ix_villages_district_id_name_key", "district_id", "name_key"),
        enum_check("status", GeoStatus, name="villages_status"),
    )


class VillageAliasRow(Auditable, Base):
    """Alternative names, kept as their own records rather than merged into the
    name -- 'صدوار' and 'سبزوار' are the same village under two names, and both
    must remain searchable."""

    __tablename__ = "village_aliases"

    village_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("villages.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("village_id", "name_key", name="uq_village_aliases_village_id_name_key"),
    )


class StationRow(Auditable, Base):
    __tablename__ = "stations"

    code: Mapped[str] = mapped_column(String(32), nullable=False)      # GRB-SYG-001-S1
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    village_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("villages.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    district_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("districts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    latitude: Mapped[Decimal | None] = mapped_column(_LAT)
    longitude: Mapped[Decimal | None] = mapped_column(_LON)
    description: Mapped[str | None] = mapped_column(Text)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(12), default=GeoStatus.ACTIVE.value, nullable=False)

    __table_args__ = (
        UniqueConstraint("code", name="uq_stations_code"),
        Index("ix_stations_latitude_longitude", "latitude", "longitude"),
        enum_check("status", GeoStatus, name="stations_status"),
    )


class DestinationRow(Auditable, Base):
    """Charikar, Qarabagh and Kabul are rows here, never constants in code.
    Kabul owns Khair Khana Mina and Jada through parent_id."""

    __tablename__ = "destinations"

    code: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    name_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("destinations.id", ondelete="RESTRICT"), index=True
    )
    district_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("districts.id", ondelete="RESTRICT"), index=True
    )
    station_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stations.id", ondelete="RESTRICT"), index=True
    )
    latitude: Mapped[Decimal | None] = mapped_column(_LAT)
    longitude: Mapped[Decimal | None] = mapped_column(_LON)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(12), default=GeoStatus.ACTIVE.value, nullable=False)

    __table_args__ = (
        UniqueConstraint("code", name="uq_destinations_code"),
        enum_check("kind", DestinationKind, name="destinations_kind"),
        enum_check("status", GeoStatus, name="destinations_status"),
    )


class PlaceRow(Auditable, Base):
    """A name a passenger gave to the spot they were standing on.

    Anonymous by construction (ADR 0015): there is no user column, and
    ``created_by`` is never written. A row says "people call this spot X",
    never "this passenger stood here" -- the second is a trail, and a trail of
    where a woman goes is not a thing VELRO holds, which is what the privacy
    page promises passengers about their location.

    One row per place, not per report: a second passenger naming the same
    spot the same way adds to ``report_count`` rather than a row, so the table
    grows with the valley's places and not with its traffic.
    """

    __tablename__ = "places"

    #: What the passenger typed, minus only invisible characters.
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    #: `domain.text.comparison_key` of the name, for matching reports and
    #: known villages across keyboards.
    name_key: Mapped[str] = mapped_column(String(80), nullable=False)
    #: Inferred from the GPS fix, never chosen: the nearest station's district.
    district_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("districts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    #: The known village this name matched, when it matched one -- which is
    #: what approved it without a person reading it.
    village_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("villages.id", ondelete="RESTRICT"), index=True
    )
    #: Where a passenger here actually boards.
    nearest_station_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("stations.id", ondelete="RESTRICT"), index=True
    )
    latitude: Mapped[Decimal] = mapped_column(_LAT, nullable=False)
    longitude: Mapped[Decimal] = mapped_column(_LON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), default=PlaceStatus.PENDING.value, nullable=False
    )
    report_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # "Is this name already here?" -- asked on every report.
        Index("ix_places_district_id_name_key", "district_id", "name_key"),
        Index("ix_places_latitude_longitude", "latitude", "longitude"),
        CheckConstraint("report_count > 0", name="places_report_count_positive"),
        enum_check("status", PlaceStatus, name="places_status"),
    )
