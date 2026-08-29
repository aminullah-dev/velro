"""Driver, vehicle and location repositories."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from domain.enums import (
    DocumentStatus,
    DriverApprovalStatus,
    DriverAvailability,
    VehicleStatus,
)
from infrastructure.db.models.supply import (
    DriverDocumentRow,
    DriverLocationRow,
    DriverRow,
    VehicleRow,
)
from infrastructure.db.repositories.base import SqlRepository
from shared import error_codes


class DriverRepository(SqlRepository[DriverRow]):
    model = DriverRow
    not_found_code = error_codes.DRIVER_NOT_FOUND

    def find_by_user(self, user_id: str) -> DriverRow | None:
        return self.find_by(user_id=user_id)

    def documents_of(self, driver_id: str) -> list[DriverDocumentRow]:
        stmt = select(DriverDocumentRow).where(
            DriverDocumentRow.driver_id == driver_id,
            DriverDocumentRow.deleted_at.is_(None),
        )
        return list(self.session.scalars(stmt).all())

    def available_for(self, *, limit: int = 20) -> list[DriverRow]:
        """Approved and online. The one gate every dispatch path passes."""
        stmt = (
            self._base()
            .where(
                DriverRow.approval_status == DriverApprovalStatus.APPROVED.value,
                DriverRow.availability == DriverAvailability.ONLINE.value,
            )
            .limit(min(limit, 100))
        )
        return list(self.session.scalars(stmt).all())

    def record_rating(self, driver_id: str, score: int) -> None:
        row = self.get(driver_id)
        row.rating_sum += score
        row.rating_count += 1
        row.version += 1
        self.session.add(row)


class DriverDocumentRepository(SqlRepository[DriverDocumentRow]):
    """Documents, newest first.

    Every upload is kept. A driver needs to see why an earlier attempt was
    rejected, and an administrator needs to see what was originally sent.
    """

    model = DriverDocumentRow
    not_found_code = error_codes.DOCUMENT_NOT_FOUND

    def create(self, **fields) -> DriverDocumentRow:
        row = DriverDocumentRow(**fields)
        self.session.add(row)
        return row

    def for_driver(self, driver_id: str) -> list[DriverDocumentRow]:
        stmt = (
            self._base()
            .where(DriverDocumentRow.driver_id == driver_id)
            .order_by(DriverDocumentRow.created_at.desc())
        )
        return list(self.session.scalars(stmt).all())

    def current_for(self, driver_id: str, document_type_code: str) -> DriverDocumentRow | None:
        """The newest upload of one type -- what an administrator reviews."""
        stmt = (
            self._base()
            .where(
                DriverDocumentRow.driver_id == driver_id,
                DriverDocumentRow.document_type_code == document_type_code,
            )
            .order_by(DriverDocumentRow.created_at.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).one_or_none()

    def pending_count(self) -> int:
        from sqlalchemy import func, select

        stmt = (
            select(func.count())
            .select_from(DriverDocumentRow)
            .where(
                DriverDocumentRow.deleted_at.is_(None),
                DriverDocumentRow.status == DocumentStatus.PENDING.value,
            )
        )
        return int(self.session.scalar(stmt) or 0)


class VehicleRepository(SqlRepository[VehicleRow]):
    model = VehicleRow
    not_found_code = error_codes.VEHICLE_NOT_FOUND

    def primary_for_driver(self, driver_id: str) -> VehicleRow | None:
        stmt = (
            self._base()
            .where(
                VehicleRow.driver_id == driver_id,
                VehicleRow.status == VehicleStatus.ACTIVE.value,
            )
            .order_by(VehicleRow.created_at)
            .limit(1)
        )
        return self.session.scalars(stmt).one_or_none()

    def find_by_plate(self, plate_number: str) -> VehicleRow | None:
        return self.find_by(plate_number=plate_number)


class DriverLocationRepository:
    """One current position per driver, upserted.

    Deliberately not a history table: dispatch reads this on every match, and a
    growing trail would make the hot query slower every week.
    """

    def __init__(self, session) -> None:
        self.session = session

    def upsert(
        self,
        *,
        driver_id: str,
        latitude: Decimal,
        longitude: Decimal,
        recorded_at: datetime,
        heading_degrees: int | None = None,
        accuracy_m: int | None = None,
        trip_id: str | None = None,
    ) -> DriverLocationRow:
        from shared.ids import new_id

        row = self.session.scalars(
            select(DriverLocationRow).where(DriverLocationRow.driver_id == driver_id)
        ).one_or_none()
        if row is None:
            row = DriverLocationRow(id=new_id(), driver_id=driver_id,
                                    latitude=latitude, longitude=longitude,
                                    recorded_at=recorded_at)
            self.session.add(row)
        else:
            # A ping that arrived out of order must not move the driver backwards.
            if row.recorded_at and recorded_at < row.recorded_at:
                return row
            row.latitude = latitude
            row.longitude = longitude
            row.recorded_at = recorded_at
            row.version += 1
        row.heading_degrees = heading_degrees
        row.accuracy_m = accuracy_m
        row.trip_id = trip_id
        return row

    def find(self, driver_id: str) -> DriverLocationRow | None:
        return self.session.scalars(
            select(DriverLocationRow).where(DriverLocationRow.driver_id == driver_id)
        ).one_or_none()
