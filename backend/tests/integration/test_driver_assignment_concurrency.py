"""One trip, one driver -- under real concurrency.

The seat race next door proves two passengers cannot both buy the last seat.
These prove the same shape of guarantee for the other side of the vehicle:
two drivers cannot both win one trip, and one driver cannot win two trips at
once. Real threads, real connections, a real PostgreSQL, because the defect
each of these closes was invisible to every sequential test the project had.

AcceptTrip's own docstring said the trip row was locked. The code read it
with ``get``. Two accepts in the same instant both saw SCHEDULED, both
assigned themselves, the last commit owned ``driver_id``, and both handsets
told their driver to go -- two cars to one station, one of them to nobody.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, select

from application.use_cases.dispatch import AcceptTrip, AcceptTripCommand
from application.use_cases.negotiate_fare import AcceptOffer, AcceptOfferCommand
from domain.driver import normalise_plate
from domain.enums import (
    DestinationKind,
    DriverApprovalStatus,
    DriverAvailability,
    FareOfferStatus,
    RideKind,
    RideRequestStatus,
    RouteStatus,
    RouteType,
    TripStatus,
    VehicleStatus,
)
from infrastructure.db.models.geography import (
    DestinationRow,
    DistrictRow,
    ProvinceRow,
    StationRow,
    VillageRow,
)
from infrastructure.db.models.identity import UserRow
from infrastructure.db.models.ops import NumberSequenceRow
from infrastructure.db.models.routing import RouteRow
from infrastructure.db.models.supply import DriverRow, VehicleRow
from infrastructure.db.models.trips import FareOfferRow, RideRequestRow, TripRow, TripSeatRow
from infrastructure.db.repositories.geography import GeographyRepository
from infrastructure.db.repositories.routing import RouteRepository
from infrastructure.db.repositories.seats import TripSeatRepository
from infrastructure.db.repositories.supply import DriverRepository, VehicleRepository
from infrastructure.db.repositories.trips import (
    BookingRepository,
    DispatchOfferRepository,
    FareOfferRepository,
    RideRequestRepository,
    TripRepository,
)
from infrastructure.db.session import UnitOfWork
from infrastructure.services.audit import SqlAuditLog
from infrastructure.services.codes import SecretsVerificationCodeGenerator
from infrastructure.services.numbers import SqlNumberAllocator
from shared.clock import SystemClock
from shared.errors import ConflictError
from shared.ids import new_id

pytestmark = pytest.mark.integration


# -- building the world ---------------------------------------------------

def _places(session) -> dict[str, str]:
    """A station and a destination with every foreign key behind them real."""
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
    for row in (province, district, village, station, destination, route):
        session.add(row)
        session.flush()
    return {"station_id": station.id, "destination_id": destination.id, "route_id": route.id}


def _scheduled_trip(session, places: dict[str, str], *, capacity: int = 4) -> str:
    trip = TripRow(
        id=new_id(), number=f"VLR-2026-{new_id()[-12:]}", route_id=places["route_id"],
        ride_kind=RideKind.SHARED.value, seat_capacity=capacity,
        scheduled_departure_at=datetime.now(UTC) + timedelta(hours=2),
        status=TripStatus.SCHEDULED.value, origin_station_id=places["station_id"],
        destination_id=places["destination_id"],
    )
    session.add(trip)
    session.flush()
    session.add_all(
        TripSeatRow(id=new_id(), trip_id=trip.id, seat_number=n) for n in range(1, capacity + 1)
    )
    session.flush()
    return trip.id


def _person(session, name: str) -> str:
    user = UserRow(id=new_id(), phone=f"+9370{new_id()[-7:]}", full_name=name)
    session.add(user)
    session.flush()
    return user.id


def _road_ready_driver(session, name: str, plate: str) -> tuple[str, str]:
    """Approved, online, with an active car: everything AcceptTrip asks for.
    Returns (user_id, driver_id)."""
    user_id = _person(session, name)
    driver = DriverRow(
        id=new_id(), user_id=user_id,
        approval_status=DriverApprovalStatus.APPROVED.value,
        availability=DriverAvailability.ONLINE.value,
    )
    session.add(driver)
    session.flush()
    session.add(
        VehicleRow(
            id=new_id(), driver_id=driver.id, vehicle_type_code="SEDAN",
            plate_number=plate, plate_key=normalise_plate(plate), seat_capacity=4,
            status=VehicleStatus.ACTIVE.value,
        )
    )
    session.flush()
    return user_id, driver.id


def _sequences(session) -> None:
    """Pre-create the year's number sequences.

    Two transactions that both find no sequence row both try to insert one,
    and the loser dies on the unique constraint -- a real behaviour, tested
    elsewhere, and not the one under examination here.
    """
    year = datetime.now(UTC).year
    for entity, prefix in (("trip", "VLR"), ("booking", "BKG")):
        session.add(
            NumberSequenceRow(id=new_id(), entity=entity, year=year, next_value=1, prefix=prefix)
        )
    session.flush()


# -- the contenders ---------------------------------------------------------

def _accept_trip(session_factory, trip_id: str, driver_user_id: str, barrier) -> str:
    try:
        with UnitOfWork(session_factory) as uow:
            s = uow.session
            use_case = AcceptTrip(
                trips=TripRepository(s), drivers=DriverRepository(s),
                vehicles=VehicleRepository(s), offers=DispatchOfferRepository(s),
                bookings=BookingRepository(s), audit=SqlAuditLog(s, SystemClock()),
                clock=SystemClock(),
            )
            barrier.wait(timeout=10)
            use_case.execute(AcceptTripCommand(trip_id=trip_id, driver_user_id=driver_user_id))
        return "WON"
    except ConflictError as exc:
        return f"LOST:{exc.code}"


def _accept_offer(session_factory, offer_id: str, passenger_id: str, barrier) -> str:
    try:
        with UnitOfWork(session_factory) as uow:
            s = uow.session
            use_case = AcceptOffer(
                requests=RideRequestRepository(s), offers=FareOfferRepository(s),
                trips=TripRepository(s), bookings=BookingRepository(s),
                seats=TripSeatRepository(s), drivers=DriverRepository(s),
                vehicles=VehicleRepository(s), routes=RouteRepository(s),
                geography=GeographyRepository(s), numbers=SqlNumberAllocator(s),
                codes=SecretsVerificationCodeGenerator(4),
                audit=SqlAuditLog(s, SystemClock()), clock=SystemClock(), new_id=new_id,
            )
            barrier.wait(timeout=10)
            use_case.execute(AcceptOfferCommand(offer_id=offer_id, passenger_id=passenger_id))
        return "WON"
    except ConflictError as exc:
        return f"LOST:{exc.code}"


def _race(calls):
    barrier = threading.Barrier(len(calls))
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(lambda call: call(barrier), calls))


# -- the guarantees ----------------------------------------------------------

@pytest.mark.usefixtures("clean_database")
def test_two_drivers_cannot_both_win_one_trip(engine: Engine, session_factory) -> None:
    with session_factory() as session:
        places = _places(session)
        trip_id = _scheduled_trip(session, places)
        first_user, first_driver = _road_ready_driver(session, "محمد", "PRW-1111")
        second_user, second_driver = _road_ready_driver(session, "نجیب", "PRW-2222")
        session.commit()

    results = _race([
        lambda b: _accept_trip(session_factory, trip_id, first_user, b),
        lambda b: _accept_trip(session_factory, trip_id, second_user, b),
    ])

    assert sorted(results) == ["LOST:TRIP_DRIVER_ALREADY_ASSIGNED", "WON"], results

    with session_factory() as session:
        trip = session.get(TripRow, trip_id)
        assert trip.status == TripStatus.DRIVER_ASSIGNED.value
        assert trip.driver_id in {first_driver, second_driver}
        # Exactly one driver went on trip. The loser is still free to be
        # dispatched somewhere else, which is the point of refusing him.
        on_trip = session.scalars(
            select(DriverRow).where(DriverRow.availability == DriverAvailability.ON_TRIP.value)
        ).all()
        assert [d.id for d in on_trip] == [trip.driver_id]


@pytest.mark.usefixtures("clean_database")
def test_one_driver_cannot_win_two_trips_at_once(engine: Engine, session_factory) -> None:
    """Two offers on his screen, both thumbs at once."""
    with session_factory() as session:
        places = _places(session)
        first_trip = _scheduled_trip(session, places)
        second_trip = _scheduled_trip(session, places)
        user_id, driver_id = _road_ready_driver(session, "محمد", "PRW-1111")
        session.commit()

    results = _race([
        lambda b: _accept_trip(session_factory, first_trip, user_id, b),
        lambda b: _accept_trip(session_factory, second_trip, user_id, b),
    ])

    assert sorted(results) == ["LOST:DRIVER_ALREADY_ON_TRIP", "WON"], results

    with session_factory() as session:
        assigned = session.scalars(
            select(TripRow).where(TripRow.driver_id == driver_id)
        ).all()
        assert len(assigned) == 1
        untouched = session.get(
            TripRow, second_trip if assigned[0].id == first_trip else first_trip
        )
        assert untouched.status == TripStatus.SCHEDULED.value
        assert untouched.driver_id is None


@pytest.mark.usefixtures("clean_database")
def test_two_passengers_cannot_both_hire_one_driver(engine: Engine, session_factory) -> None:
    """The negotiated path: one driver bid on two requests, both accept at once.

    Each accept holds its own request row, so the request lock says nothing
    about the driver -- this is the race the driver lock exists for.
    """
    now = datetime.now(UTC)
    with session_factory() as session:
        places = _places(session)
        _sequences(session)
        _, driver_id = _road_ready_driver(session, "محمد", "PRW-1111")
        offers: list[tuple[str, str]] = []
        for name in ("احمد", "زهرا"):
            passenger_id = _person(session, name)
            request = RideRequestRow(
                id=new_id(), passenger_id=passenger_id,
                origin_station_id=places["station_id"],
                destination_id=places["destination_id"],
                passenger_count=1, requested_for=now + timedelta(hours=2),
                expires_at=now + timedelta(hours=1),
                status=RideRequestStatus.OPEN.value,
                offered_fare_minor=90_000, offered_fare_currency="AFN",
            )
            session.add(request)
            session.flush()
            offer = FareOfferRow(
                id=new_id(), ride_request_id=request.id, driver_id=driver_id,
                amount_minor=95_000, amount_currency="AFN",
                status=FareOfferStatus.OFFERED.value,
            )
            session.add(offer)
            session.flush()
            offers.append((offer.id, passenger_id))
        session.commit()

    results = _race([
        lambda b, o=offers[0]: _accept_offer(session_factory, o[0], o[1], b),
        lambda b, o=offers[1]: _accept_offer(session_factory, o[0], o[1], b),
    ])

    assert sorted(results) == ["LOST:DRIVER_ALREADY_ON_TRIP", "WON"], results

    with session_factory() as session:
        trips = session.scalars(select(TripRow).where(TripRow.driver_id == driver_id)).all()
        assert len(trips) == 1, "one driver, one car, one journey"
        matched = session.scalars(
            select(RideRequestRow).where(
                RideRequestRow.status == RideRequestStatus.MATCHED.value
            )
        ).all()
        assert len(matched) == 1
        # The other passenger's request is still open: she lost a driver, not
        # her place on the board.
        still_open = session.scalars(
            select(RideRequestRow).where(RideRequestRow.status == RideRequestStatus.OPEN.value)
        ).all()
        assert len(still_open) == 1
