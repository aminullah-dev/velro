"""The guarantee: two passengers cannot both book the last seat.

This is the test the entire booking design exists to pass. It uses real
threads, real connections and a real PostgreSQL, because a mocked database
cannot demonstrate anything about row locking.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import IntegrityError

from domain.enums import (
    BookingStatus,
    DestinationKind,
    RideKind,
    RouteStatus,
    RouteType,
    SeatStatus,
    TripStatus,
)
from infrastructure.db.models.geography import (
    DestinationRow,
    DistrictRow,
    ProvinceRow,
    StationRow,
    VillageRow,
)
from infrastructure.db.models.identity import UserRow
from infrastructure.db.models.routing import RouteRow
from infrastructure.db.models.trips import BookingRow, BookingSeatRow, TripRow, TripSeatRow
from infrastructure.db.repositories.seats import TripSeatRepository
from infrastructure.db.session import UnitOfWork
from shared.errors import ConflictError
from shared.ids import new_id

pytestmark = pytest.mark.integration


def _passenger(session) -> str:
    user = UserRow(id=new_id(), phone=f"+9370{new_id()[-7:]}", full_name="احمد")
    session.add(user)
    session.commit()
    return user.id


def _build_trip(session, *, capacity: int) -> dict[str, str]:
    """A minimal but fully referential trip: every FK in the schema is real."""
    province = ProvinceRow(id=new_id(), code="AF-PAR", name="پروان")
    district = DistrictRow(id=new_id(), code="GRB-SYG", name="سیاه‌گرد", province_id=province.id)
    village = VillageRow(
        id=new_id(), code="GRB-SYG-001", name="خیشکی", name_key="خیشکی", district_id=district.id
    )
    station = StationRow(
        id=new_id(), code="GRB-SYG-001-S1", name="ایستگاه خیشکی", name_key="ایستگاه خیشکی",
        village_id=village.id, district_id=district.id,
    )
    destination = DestinationRow(
        id=new_id(), code="EXT-CHK", name="چاریکار", name_key="چاریکار",
        kind=DestinationKind.EXTERNAL.value,
    )
    route = RouteRow(
        id=new_id(), code="R-KHISHKI-CHARIKAR", route_type=RouteType.INTERCITY.value,
        origin_station_id=station.id, destination_id=destination.id,
        status=RouteStatus.ACTIVE.value,
    )
    trip = TripRow(
        id=new_id(), number=f"VLR-2026-{new_id()[-12:]}", route_id=route.id,
        ride_kind=RideKind.SHARED.value, seat_capacity=capacity,
        scheduled_departure_at=datetime.now(UTC) + timedelta(hours=2),
        status=TripStatus.SCHEDULED.value, origin_station_id=station.id,
        destination_id=destination.id,
    )
    # Flushed in dependency order. No ORM relationships are declared anywhere in
    # this codebase -- repositories return domain objects, not object graphs --
    # so the session has no basis on which to sort these inserts itself.
    for row in (province, district, village, station, destination, route, trip):
        session.add(row)
        session.flush()
    session.add_all(
        TripSeatRow(id=new_id(), trip_id=trip.id, seat_number=n)
        for n in range(1, capacity + 1)
    )
    session.commit()
    return {
        "trip_id": trip.id,
        "station_id": station.id,
        "destination_id": destination.id,
    }


def _make_booking(session, ctx: dict[str, str], *, seat_count: int) -> str:
    booking_id = new_id()
    session.add(
        BookingRow(
            id=booking_id,
            number=f"BKG-2026-{booking_id[-12:]}",
            trip_id=ctx["trip_id"],
            passenger_id=ctx["passenger_id"],
            ride_kind=RideKind.SHARED.value,
            seat_count=seat_count,
            pickup_sequence=0,
            dropoff_sequence=1,
            pickup_station_id=ctx["station_id"],
            dropoff_destination_id=ctx["destination_id"],
            fare_total_minor=50_000,
            fare_total_currency="AFN",
            fare_breakdown=[{"key": "fare.component.base", "amount_minor": 50_000}],
            status=BookingStatus.CONFIRMED.value,
            verification_code=booking_id[-4:].upper(),
        )
    )
    session.flush()
    return booking_id


def _book(
    session_factory,
    trip_id: str,
    seat_count: int,
    barrier: threading.Barrier,
    *,
    trip_context: dict[str, str],
) -> str:
    """One passenger's booking attempt, released simultaneously with the others.

    Writes a real booking row before claiming seats, exactly as the use case
    does -- ``booking_seats.booking_id`` is a declared foreign key, so a test
    that invented an id would be testing a path production never takes.
    """
    booking_id = new_id()
    try:
        with UnitOfWork(session_factory) as uow:
            seats = TripSeatRepository(uow.session)
            barrier.wait(timeout=10)          # every thread arrives at the lock together
            locked = seats.lock_available(trip_id, seat_count)
            uow.session.add(
                BookingRow(
                    id=booking_id,
                    number=f"BKG-2026-{booking_id[-12:]}",
                    trip_id=trip_id,
                    passenger_id=trip_context["passenger_id"],
                    ride_kind=RideKind.SHARED.value,
                    seat_count=seat_count,
                    pickup_sequence=0,
                    dropoff_sequence=1,
                    pickup_station_id=trip_context["station_id"],
                    dropoff_destination_id=trip_context["destination_id"],
                    fare_total_minor=50_000,
                    fare_total_currency="AFN",
                    fare_breakdown=[{"key": "fare.component.base", "amount_minor": 50_000}],
                    status=BookingStatus.CONFIRMED.value,
                    verification_code=booking_id[-4:].upper(),
                )
            )
            uow.flush()
            seats.reserve(locked, booking_id)
            uow.flush()
        return "WON"
    except ConflictError as exc:
        return f"LOST:{exc.code}"
    except IntegrityError:
        return "LOST:UNIQUE_CONSTRAINT"


@pytest.mark.usefixtures("clean_database")
def test_only_one_passenger_wins_the_last_seat(engine: Engine, session_factory) -> None:
    contenders = 12
    with session_factory() as session:
        ctx = _build_trip(session, capacity=1)          # exactly one seat exists
        ctx["passenger_id"] = _passenger(session)
    trip_id = ctx["trip_id"]

    barrier = threading.Barrier(contenders)
    with ThreadPoolExecutor(max_workers=contenders) as pool:
        results = list(
            pool.map(
                lambda _: _book(session_factory, trip_id, 1, barrier, trip_context=ctx),
                range(contenders),
            )
        )

    winners = [r for r in results if r == "WON"]
    losers = [r for r in results if r != "WON"]

    assert len(winners) == 1, f"expected exactly one winner, got {results}"
    assert len(losers) == contenders - 1
    assert all(r.startswith("LOST:") for r in losers)

    # And the database agrees: one seat, taken once, by one booking.
    with session_factory() as session:
        seats = session.scalars(select(TripSeatRow).where(TripSeatRow.trip_id == trip_id)).all()
        assert len(seats) == 1
        assert seats[0].status == SeatStatus.RESERVED.value
        links = session.scalars(
            select(BookingSeatRow).where(BookingSeatRow.trip_seat_id == seats[0].id)
        ).all()
        assert len(links) == 1


@pytest.mark.usefixtures("clean_database")
def test_concurrent_bookings_never_oversell_a_trip(engine: Engine, session_factory) -> None:
    """Four seats, ten passengers each wanting one: exactly four succeed."""
    capacity, contenders = 4, 10
    with session_factory() as session:
        ctx = _build_trip(session, capacity=capacity)
        ctx["passenger_id"] = _passenger(session)
    trip_id = ctx["trip_id"]

    barrier = threading.Barrier(contenders)
    with ThreadPoolExecutor(max_workers=contenders) as pool:
        results = list(
            pool.map(
                lambda _: _book(session_factory, trip_id, 1, barrier, trip_context=ctx),
                range(contenders),
            )
        )

    assert results.count("WON") == capacity, results
    with session_factory() as session:
        taken = session.scalars(
            select(TripSeatRow).where(
                TripSeatRow.trip_id == trip_id,
                TripSeatRow.status == SeatStatus.RESERVED.value,
            )
        ).all()
        assert len(taken) == capacity
        assert len({s.booking_id for s in taken}) == capacity   # no seat shared


@pytest.mark.usefixtures("clean_database")
def test_multi_seat_bookings_are_all_or_nothing(engine: Engine, session_factory) -> None:
    """Three seats; two passengers each wanting two. One gets both, one gets none."""
    with session_factory() as session:
        ctx = _build_trip(session, capacity=3)
        ctx["passenger_id"] = _passenger(session)
    trip_id = ctx["trip_id"]

    barrier = threading.Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: _book(session_factory, trip_id, 2, barrier, trip_context=ctx),
                range(2),
            )
        )

    assert results.count("WON") == 1, results
    with session_factory() as session:
        reserved = session.scalars(
            select(TripSeatRow).where(
                TripSeatRow.trip_id == trip_id,
                TripSeatRow.status == SeatStatus.RESERVED.value,
            )
        ).all()
        # Never a partial allocation: the loser left no half-booked seat behind.
        assert len(reserved) == 2
        assert len({s.booking_id for s in reserved}) == 1


@pytest.mark.usefixtures("clean_database")
def test_unique_constraint_stops_a_double_link_even_without_the_lock(
    engine: Engine, session_factory
) -> None:
    """The backstop, tested directly.

    Bypasses ``lock_available`` entirely and tries to attach the same seat to two
    bookings. The database must refuse, so that the invariant survives this
    repository being rewritten by someone who does not read the comment.
    """
    with session_factory() as session:
        ctx = _build_trip(session, capacity=1)
        ctx["passenger_id"] = _passenger(session)
        trip_id = ctx["trip_id"]
        seat = session.scalars(
            select(TripSeatRow).where(TripSeatRow.trip_id == trip_id)
        ).one()

        first = _make_booking(session, ctx, seat_count=1)
        second = _make_booking(session, ctx, seat_count=1)

        session.add(
            BookingSeatRow(
                id=new_id(), booking_id=first, trip_seat_id=seat.id, seat_number=1
            )
        )
        session.commit()

        with pytest.raises(IntegrityError):
            session.add(
                BookingSeatRow(
                    id=new_id(), booking_id=second, trip_seat_id=seat.id, seat_number=1
                )
            )
            session.commit()
