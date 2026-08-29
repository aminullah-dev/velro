"""Trip and booking repositories."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from domain.enums import BookingStatus, TripStatus
from domain.lifecycles import BOOKABLE_TRIP_STATUSES
from infrastructure.db.models.trips import (
    BookingRow,
    BookingSeatRow,
    DispatchOfferRow,
    RideRequestRow,
    TripRow,
    TripStopRow,
)
from infrastructure.db.repositories.base import SqlRepository
from shared import error_codes

_ACTIVE_BOOKING_STATUSES = tuple(
    s.value
    for s in (
        BookingStatus.PENDING,
        BookingStatus.CONFIRMED,
        BookingStatus.DRIVER_ASSIGNED,
        BookingStatus.READY,
        BookingStatus.ONBOARD,
    )
)


class TripRepository(SqlRepository[TripRow]):
    model = TripRow
    not_found_code = error_codes.TRIP_NOT_FOUND

    def find_by_number(self, number: str) -> TripRow | None:
        return self.find_by(number=number)

    def create(self, **fields) -> TripRow:
        row = TripRow(**fields)
        self.session.add(row)
        return row

    def stops_of(self, trip_id: str) -> list[TripStopRow]:
        stmt = (
            select(TripStopRow)
            .where(TripStopRow.trip_id == trip_id, TripStopRow.deleted_at.is_(None))
            .order_by(TripStopRow.sequence)
        )
        return list(self.session.scalars(stmt).all())

    def search(
        self,
        *,
        route_ids: list[str],
        departure_from: datetime,
        departure_to: datetime,
        ride_kind: str | None = None,
        limit: int = 50,
    ) -> list[TripRow]:
        if not route_ids:
            return []
        stmt = (
            self._base()
            .where(
                TripRow.route_id.in_(route_ids),
                TripRow.scheduled_departure_at.between(departure_from, departure_to),
                TripRow.status.in_(tuple(s.value for s in BOOKABLE_TRIP_STATUSES)),
            )
            .order_by(TripRow.scheduled_departure_at)
            .limit(min(limit, 100))
        )
        if ride_kind:
            stmt = stmt.where(TripRow.ride_kind == ride_kind)
        return list(self.session.scalars(stmt).all())

    def active_for_driver(self, driver_id: str) -> TripRow | None:
        """A driver has at most one trip in flight. Enforced by the dispatch
        path, checked here so a stale client cannot start a second."""
        in_flight = (
            TripStatus.DRIVER_ASSIGNED, TripStatus.DRIVER_ARRIVING,
            TripStatus.ARRIVED_AT_PICKUP, TripStatus.BOARDING, TripStatus.IN_TRANSIT,
            TripStatus.ARRIVED,
        )
        stmt = (
            self._base()
            .where(
                TripRow.driver_id == driver_id,
                TripRow.status.in_(tuple(s.value for s in in_flight)),
            )
            .order_by(TripRow.scheduled_departure_at)
            .limit(1)
        )
        return self.session.scalars(stmt).one_or_none()

    def seats_available_map(self, trip_ids: list[str]) -> dict[str, int]:
        """Availability for a list of trips in one query.

        The search screen renders 'N seats left' for every result; doing this
        per trip is the classic N+1 that makes a list screen slow on the exact
        connection where it matters most.
        """
        if not trip_ids:
            return {}
        from infrastructure.db.models.trips import TripSeatRow

        stmt = (
            select(TripSeatRow.trip_id, func.count())
            .where(
                TripSeatRow.trip_id.in_(trip_ids),
                TripSeatRow.status == "AVAILABLE",
                TripSeatRow.booking_id.is_(None),
                TripSeatRow.deleted_at.is_(None),
            )
            .group_by(TripSeatRow.trip_id)
        )
        counts = {trip_id: int(n) for trip_id, n in self.session.execute(stmt).all()}
        return {trip_id: counts.get(trip_id, 0) for trip_id in trip_ids}


class BookingRepository(SqlRepository[BookingRow]):
    model = BookingRow
    not_found_code = error_codes.BOOKING_NOT_FOUND

    def find_by_number(self, number: str) -> BookingRow | None:
        return self.find_by(number=number)

    def create(self, **fields) -> BookingRow:
        row = BookingRow(**fields)
        self.session.add(row)
        return row

    def list_for_passenger(
        self, passenger_id: str, *, limit: int = 20, offset: int = 0
    ) -> list[BookingRow]:
        stmt = (
            self._base()
            .where(BookingRow.passenger_id == passenger_id)
            .order_by(BookingRow.created_at.desc())
            .limit(min(limit, 100))
            .offset(offset)
        )
        return list(self.session.scalars(stmt).all())

    def list_for_trip(self, trip_id: str) -> list[BookingRow]:
        stmt = (
            self._base()
            .where(BookingRow.trip_id == trip_id)
            .order_by(BookingRow.created_at)
        )
        return list(self.session.scalars(stmt).all())

    def active_for_trip(self, trip_id: str) -> list[BookingRow]:
        stmt = self._base().where(
            BookingRow.trip_id == trip_id,
            BookingRow.status.in_(_ACTIVE_BOOKING_STATUSES),
        )
        return list(self.session.scalars(stmt).all())

    def count_active_for_passenger(self, passenger_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(BookingRow)
            .where(
                BookingRow.passenger_id == passenger_id,
                BookingRow.deleted_at.is_(None),
                BookingRow.status.in_(_ACTIVE_BOOKING_STATUSES),
            )
        )
        return int(self.session.scalar(stmt) or 0)

    def find_by_verification_code(self, trip_id: str, code: str) -> BookingRow | None:
        """Used by the driver to find whose booking a presented code belongs to.

        Scoped to the trip: codes are short, and a code only has to be unique
        among the handful of people in one vehicle.
        """
        stmt = self._base().where(
            BookingRow.trip_id == trip_id,
            func.upper(BookingRow.verification_code) == code.strip().upper(),
            BookingRow.status.in_(_ACTIVE_BOOKING_STATUSES),
        )
        return self.session.scalars(stmt).one_or_none()

    def seats_of(self, booking_id: str) -> list[BookingSeatRow]:
        stmt = (
            select(BookingSeatRow)
            .where(
                BookingSeatRow.booking_id == booking_id,
                BookingSeatRow.deleted_at.is_(None),
            )
            .order_by(BookingSeatRow.seat_number)
        )
        return list(self.session.scalars(stmt).all())


class RideRequestRepository(SqlRepository[RideRequestRow]):
    model = RideRequestRow
    not_found_code = error_codes.TRIP_NOT_FOUND

    def create(self, **fields) -> RideRequestRow:
        row = RideRequestRow(**fields)
        self.session.add(row)
        return row


class DispatchOfferRepository(SqlRepository[DispatchOfferRow]):
    model = DispatchOfferRow
    not_found_code = error_codes.TRIP_NOT_FOUND

    def create(self, **fields) -> DispatchOfferRow:
        row = DispatchOfferRow(**fields)
        self.session.add(row)
        return row

    def open_for_driver(self, driver_id: str, *, at: datetime) -> list[DispatchOfferRow]:
        stmt = (
            self._base()
            .where(
                DispatchOfferRow.driver_id == driver_id,
                DispatchOfferRow.responded_at.is_(None),
                DispatchOfferRow.expires_at > at,
            )
            .order_by(DispatchOfferRow.offered_at)
        )
        return list(self.session.scalars(stmt).all())

    def find_open(self, trip_id: str, driver_id: str, *, at: datetime) -> DispatchOfferRow | None:
        stmt = self._base().where(
            DispatchOfferRow.trip_id == trip_id,
            DispatchOfferRow.driver_id == driver_id,
            DispatchOfferRow.responded_at.is_(None),
            DispatchOfferRow.expires_at > at,
        )
        return self.session.scalars(stmt).first()
