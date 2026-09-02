"""Trip and booking repositories."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select, update

from domain.enums import (
    BookingStatus,
    FareOfferStatus,
    RideRequestStatus,
    TripStatus,
)
from domain.lifecycles import BOOKABLE_TRIP_STATUSES
from domain.text import normalise_digits
from infrastructure.db.models.trips import (
    BookingRow,
    BookingSeatRow,
    DispatchOfferRow,
    FareOfferRow,
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

    def needing_driver(
        self,
        *,
        now: datetime,
        horizon: timedelta,
        overdue: timedelta = timedelta(hours=1),
        limit: int = 200,
    ) -> list[TripRow]:
        """The dispatcher's list: trips with nobody to drive them, soonest first.

        Bounded in time at both ends. Ahead, by the horizon the dispatcher is
        working to; behind, by an hour -- a trip that should have left a
        little while ago and still has no driver is still a trip somebody is
        waiting for, but one from last week is a record, not a job. Filtered
        and ordered in SQL: the previous version fetched "the first hundred
        driverless trips" in no particular order and filtered in Python, so
        once a hundred cancelled or completed trips existed the real ones
        fell off the end of the page.
        """
        stmt = (
            self._base()
            .where(
                TripRow.driver_id.is_(None),
                TripRow.status.in_(
                    (TripStatus.SCHEDULED.value, TripStatus.REQUESTED.value)
                ),
                TripRow.scheduled_departure_at >= now - overdue,
                TripRow.scheduled_departure_at <= now + horizon,
            )
            .order_by(TripRow.scheduled_departure_at)
            .limit(min(limit, 200))
        )
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

    def place_names(self, trip_ids: list[str]) -> dict[str, tuple[str | None, str | None]]:
        """(origin station name, destination name) per trip.

        One query for a list rather than one per row: the driver's board renders
        several of these, and a name lookup per card is how a screen on a slow
        connection becomes a screen that never finishes.
        """
        if not trip_ids:
            return {}
        from sqlalchemy import select

        from infrastructure.db.models.geography import DestinationRow, StationRow

        stmt = (
            select(TripRow.id, StationRow.name, DestinationRow.name)
            .join(StationRow, StationRow.id == TripRow.origin_station_id, isouter=True)
            .join(DestinationRow, DestinationRow.id == TripRow.destination_id, isouter=True)
            .where(TripRow.id.in_(trip_ids))
        )
        return {
            trip_id: (origin, destination)
            for trip_id, origin, destination in self.session.execute(stmt).all()
        }

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
        self,
        passenger_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
        statuses: list[str] | None = None,
    ) -> list[BookingRow]:
        stmt = self._base().where(BookingRow.passenger_id == passenger_id)
        if statuses:
            stmt = stmt.where(BookingRow.status.in_(statuses))
        stmt = (
            # Newest first, tie-broken on id: two bookings made in one commit
            # share a timestamp, and without the tiebreak a page boundary can
            # repeat or drop one.
            stmt.order_by(BookingRow.created_at.desc(), BookingRow.id.desc())
            .limit(min(limit, 100))
            .offset(offset)
        )
        return list(self.session.scalars(stmt).all())

    def seats_for_bookings(self, booking_ids) -> dict[str, list[int]]:
        """Seat numbers for a page of bookings, in one query.

        The list screen needs them for every row; asking per booking turns a
        history page into twenty round trips.
        """
        wanted = [i for i in set(booking_ids) if i]
        if not wanted:
            return {}
        rows = self.session.execute(
            select(BookingSeatRow.booking_id, BookingSeatRow.seat_number).where(
                BookingSeatRow.booking_id.in_(wanted),
                BookingSeatRow.deleted_at.is_(None),
            )
        ).all()
        out: dict[str, list[int]] = {}
        for booking_id, seat_number in rows:
            out.setdefault(booking_id, []).append(seat_number)
        return out

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

    def count_completed_for_passenger(self, passenger_id: str) -> int:
        """Journeys taken, not journeys booked.

        Cancellations and no-shows are excluded: a passenger's own profile
        should not count a ride they never took, and a number that flatters is
        worse than no number.
        """
        return self.session.scalar(
            select(func.count())
            .select_from(BookingRow)
            .where(
                BookingRow.passenger_id == passenger_id,
                BookingRow.status == BookingStatus.COMPLETED.value,
                BookingRow.deleted_at.is_(None),
            )
        ) or 0

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
            # Eastern digits folded before comparing. Python's upper() maps
            # no digits at all, so a driver typing ۲ on a Persian keyboard
            # could never match a code containing 2 -- and 68% of codes
            # contain a digit. Folded here as well as in the app because the
            # handsets already in Ghorband carry the build that did not.
            func.upper(BookingRow.verification_code)
            == normalise_digits(code).strip().upper(),
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
    not_found_code = error_codes.RIDE_REQUEST_NOT_FOUND

    def create(self, **fields) -> RideRequestRow:
        row = RideRequestRow(**fields)
        self.session.add(row)
        self.session.flush()
        return row

    def find_open_for_passenger(
        self, passenger_id: str, *, at: datetime | None = None
    ) -> RideRequestRow | None:
        """The one request a passenger already has in the air, if any.

        ``at`` excludes ones that have run out of time. Without it a request
        nobody answered blocks the passenger from ever asking again, which is
        the app silently breaking for them with nothing they can do about it.
        """
        stmt = self._base().where(
            RideRequestRow.passenger_id == passenger_id,
            RideRequestRow.status == RideRequestStatus.OPEN.value,
        )
        if at is not None:
            stmt = stmt.where(RideRequestRow.expires_at > at)
        return self.session.scalars(
            stmt.order_by(RideRequestRow.created_at.desc())
        ).first()

    def expire_stale_for_passenger(self, passenger_id: str, *, at: datetime) -> int:
        """Close this passenger's requests that ran out of time.

        Scoped to one passenger rather than sweeping the table: this runs on an
        ordinary read, and a request should be closed by someone looking at it,
        not by whoever happens to open the app next.
        """
        result = self.session.execute(
            update(RideRequestRow)
            .where(
                RideRequestRow.passenger_id == passenger_id,
                RideRequestRow.status == RideRequestStatus.OPEN.value,
                RideRequestRow.expires_at <= at,
                RideRequestRow.deleted_at.is_(None),
            )
            .values(status=RideRequestStatus.EXPIRED.value)
        )
        return int(result.rowcount or 0)

    def list_for_passenger(
        self, passenger_id: str, *, limit: int = 20
    ) -> list[RideRequestRow]:
        return list(
            self.session.scalars(
                self._base()
                .where(RideRequestRow.passenger_id == passenger_id)
                .order_by(RideRequestRow.created_at.desc(), RideRequestRow.id.desc())
                .limit(min(limit, 50))
            ).all()
        )

    def open_board(
        self, *, station_ids=None, at: datetime | None = None, limit: int = 50
    ) -> list[RideRequestRow]:
        """What a driver sees: open requests that have not run out of time.

        Filtered by station when the driver has a home station, because a
        request from three valleys away is noise they have to read past.
        """
        stmt = self._base().where(RideRequestRow.status == RideRequestStatus.OPEN.value)
        if at is not None:
            stmt = stmt.where(RideRequestRow.expires_at > at)
        ids = [i for i in (station_ids or []) if i]
        if ids:
            stmt = stmt.where(RideRequestRow.origin_station_id.in_(ids))
        return list(
            self.session.scalars(
                # Oldest first: someone has been waiting longest.
                stmt.order_by(RideRequestRow.created_at.asc()).limit(min(limit, 100))
            ).all()
        )

    def expire_stale(self, *, at: datetime) -> int:
        """Close requests nobody answered in time."""
        result = self.session.execute(
            update(RideRequestRow)
            .where(
                RideRequestRow.status == RideRequestStatus.OPEN.value,
                RideRequestRow.expires_at <= at,
                RideRequestRow.deleted_at.is_(None),
            )
            .values(status=RideRequestStatus.EXPIRED.value)
        )
        return int(result.rowcount or 0)


class FareOfferRepository(SqlRepository[FareOfferRow]):
    model = FareOfferRow
    not_found_code = error_codes.FARE_OFFER_NOT_FOUND

    def create(self, **fields) -> FareOfferRow:
        row = FareOfferRow(**fields)
        self.session.add(row)
        self.session.flush()
        return row

    def open_for(self, ride_request_id: str, driver_id: str) -> FareOfferRow | None:
        return self.session.scalars(
            self._base().where(
                FareOfferRow.ride_request_id == ride_request_id,
                FareOfferRow.driver_id == driver_id,
                FareOfferRow.status == FareOfferStatus.OFFERED.value,
            )
        ).first()

    def for_request(self, ride_request_id: str) -> list[FareOfferRow]:
        """Every offer on a request, cheapest first.

        Cheapest first because that is what a passenger came to compare; the
        screen still shows the rating beside each, so cheapest is a default
        order rather than a recommendation.
        """
        return list(
            self.session.scalars(
                self._base()
                .where(FareOfferRow.ride_request_id == ride_request_id)
                .order_by(FareOfferRow.amount_minor.asc(), FareOfferRow.created_at.asc())
            ).all()
        )

    def open_for_driver(self, driver_id: str, *, limit: int = 20) -> list[FareOfferRow]:
        return list(
            self.session.scalars(
                self._base()
                .where(
                    FareOfferRow.driver_id == driver_id,
                    FareOfferRow.status == FareOfferStatus.OFFERED.value,
                )
                .order_by(FareOfferRow.created_at.desc())
                .limit(min(limit, 50))
            ).all()
        )

    def decline_others(self, *, request_id: str, except_id: str, at: datetime) -> int:
        """Tell every other driver at once that the request is taken.

        Without this they keep an offer that can never be accepted, and find out
        only by driving to a station where nobody is waiting.
        """
        result = self.session.execute(
            update(FareOfferRow)
            .where(
                FareOfferRow.ride_request_id == request_id,
                FareOfferRow.id != except_id,
                FareOfferRow.status == FareOfferStatus.OFFERED.value,
            )
            .values(status=FareOfferStatus.DECLINED.value, responded_at=at)
        )
        return int(result.rowcount or 0)


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

    def open_for_trips(
        self, trip_ids: list[str], *, at: datetime
    ) -> dict[str, list[DispatchOfferRow]]:
        """Every offer still on a driver's screen, per trip, in one query."""
        wanted = [i for i in set(trip_ids) if i]
        if not wanted:
            return {}
        rows = self.session.scalars(
            self._base().where(
                DispatchOfferRow.trip_id.in_(wanted),
                DispatchOfferRow.responded_at.is_(None),
                DispatchOfferRow.expires_at > at,
            )
        ).all()
        out: dict[str, list[DispatchOfferRow]] = {}
        for row in rows:
            out.setdefault(row.trip_id, []).append(row)
        return out

    def find_open(self, trip_id: str, driver_id: str, *, at: datetime) -> DispatchOfferRow | None:
        stmt = self._base().where(
            DispatchOfferRow.trip_id == trip_id,
            DispatchOfferRow.driver_id == driver_id,
            DispatchOfferRow.responded_at.is_(None),
            DispatchOfferRow.expires_at > at,
        )
        return self.session.scalars(stmt).first()
