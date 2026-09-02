"""Money moves once, whatever two hands do at the same instant.

Two of the questions to ask on the first day with real users: can a
settlement be paid twice, and can a cancellation be recorded twice? Both
paths read their row without a lock, so the honest answer was yes -- two
operators, or one operator's double-click on a slow connection, both saw
the state before either commit and both acted on it. Real threads, real
connections, a real PostgreSQL.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import Engine, select

from application.use_cases.cancel_booking import CancelBooking, CancelBookingCommand
from application.use_cases.settlements import DecideSettlement, DecideSettlementCommand
from domain.enums import (
    ActorRole,
    BookingStatus,
    DestinationKind,
    DriverApprovalStatus,
    RideKind,
    RouteStatus,
    RouteType,
    SeatStatus,
    SettlementDirection,
    SettlementStatus,
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
from infrastructure.db.models.money import SettlementRow, WalletRow
from infrastructure.db.models.ops import CancellationRow
from infrastructure.db.models.routing import RouteRow
from infrastructure.db.models.supply import DriverRow
from infrastructure.db.models.trips import BookingRow, BookingSeatRow, TripRow, TripSeatRow
from infrastructure.db.repositories.money import SettlementRepository, WalletRepository
from infrastructure.db.repositories.ops import CancellationRepository
from infrastructure.db.repositories.seats import TripSeatRepository
from infrastructure.db.repositories.supply import DriverRepository
from infrastructure.db.repositories.trips import BookingRepository, TripRepository
from infrastructure.db.session import UnitOfWork
from infrastructure.services.audit import SqlAuditLog
from infrastructure.services.settings import SqlSettingsProvider
from shared.clock import SystemClock
from shared.errors import ConflictError, PermissionError
from shared.ids import new_id

pytestmark = pytest.mark.integration


def _race(calls):
    barrier = threading.Barrier(len(calls))
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(lambda call: call(barrier), calls))


# -- a payout being paid ------------------------------------------------------

def _payout_in_flight(session, amount: int) -> tuple[str, str]:
    """A driver owed `amount`, with that amount already held for a settlement
    the office is processing. Returns (settlement_id, wallet_id)."""
    user = UserRow(id=new_id(), phone=f"+9370{new_id()[-7:]}", full_name="محمد")
    session.add(user)
    session.flush()
    driver = DriverRow(
        id=new_id(), user_id=user.id, approval_status=DriverApprovalStatus.APPROVED.value,
    )
    session.add(driver)
    session.flush()
    wallet = WalletRow(
        id=new_id(), driver_id=driver.id, currency="AFN",
        available_minor=0, pending_minor=amount, lifetime_earned_minor=amount,
    )
    session.add(wallet)
    session.flush()
    settlement = SettlementRow(
        id=new_id(), driver_id=driver.id, wallet_id=wallet.id,
        reference=f"STL-2026-{new_id()[-6:]}", direction=SettlementDirection.PAYOUT.value,
        period_start=date(2026, 8, 1), period_end=date(2026, 8, 31),
        amount_minor=amount, currency="AFN", status=SettlementStatus.PROCESSING.value,
    )
    session.add(settlement)
    session.flush()
    return settlement.id, wallet.id


def _mark_paid(session_factory, settlement_id: str, barrier) -> str:
    try:
        with UnitOfWork(session_factory) as uow:
            s = uow.session
            use_case = DecideSettlement(
                wallets=WalletRepository(s), settlements=SettlementRepository(s),
                audit=SqlAuditLog(s, SystemClock()), clock=SystemClock(),
            )
            barrier.wait(timeout=10)
            use_case.execute(DecideSettlementCommand(
                settlement_id=settlement_id, to=SettlementStatus.PAID, actor_id="office",
            ))
        return "WON"
    except ConflictError as exc:
        return f"LOST:{exc.code}"


@pytest.mark.usefixtures("clean_database")
def test_a_payout_cannot_be_paid_twice(engine: Engine, session_factory) -> None:
    amount = 120_000
    with session_factory() as session:
        settlement_id, wallet_id = _payout_in_flight(session, amount)
        session.commit()

    results = _race([
        lambda b: _mark_paid(session_factory, settlement_id, b),
        lambda b: _mark_paid(session_factory, settlement_id, b),
    ])
    assert sorted(results) == ["LOST:SETTLEMENT_INVALID_TRANSITION", "WON"], results

    with session_factory() as session:
        wallet = session.get(WalletRow, wallet_id)
        # The hold drained exactly once: pending back to nothing, not to
        # minus the amount, and the lifetime total counts one payout.
        assert wallet.pending_minor == 0
        assert wallet.lifetime_paid_minor == amount
        assert session.get(SettlementRow, settlement_id).status == SettlementStatus.PAID.value


# -- a booking being cancelled -------------------------------------------------

def _a_driver(session) -> tuple[str, str]:
    """An approved driver with nothing else attached. Returns
    (driver_id, user_id) -- the use case's ActorRole.DRIVER commands carry the
    user id, not the driver id, so tests need both."""
    user = UserRow(id=new_id(), phone=f"+9370{new_id()[-7:]}", full_name="راننده")
    session.add(user)
    session.flush()
    driver = DriverRow(
        id=new_id(), user_id=user.id, approval_status=DriverApprovalStatus.APPROVED.value,
    )
    session.add(driver)
    session.flush()
    return driver.id, user.id


def _confirmed_booking(
    session, *, driver_id: str | None = None, passenger_id: str | None = None
) -> tuple[str, str]:
    """One passenger holding one seat on a scheduled trip. Returns
    (booking_id, passenger_id).

    ``passenger_id`` lets a caller book the seat under an *existing* user --
    the driver themselves, say -- rather than the fresh one made below."""
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
        ride_kind=RideKind.SHARED.value, seat_capacity=4,
        scheduled_departure_at=datetime.now(UTC) + timedelta(hours=6),
        status=TripStatus.SCHEDULED.value, origin_station_id=station.id,
        destination_id=destination.id, driver_id=driver_id,
    )
    rows = [province, district, village, station, destination, route, trip]
    if passenger_id is None:
        passenger = UserRow(id=new_id(), phone=f"+9370{new_id()[-7:]}", full_name="احمد")
        rows.append(passenger)
        passenger_id = passenger.id
    for row in rows:
        session.add(row)
        session.flush()
    seats = [TripSeatRow(id=new_id(), trip_id=trip.id, seat_number=n) for n in range(1, 5)]
    session.add_all(seats)
    session.flush()

    booking = BookingRow(
        id=new_id(), number=f"BKG-2026-{new_id()[-12:]}", trip_id=trip.id,
        passenger_id=passenger_id, ride_kind=RideKind.SHARED.value, seat_count=1,
        pickup_sequence=0, dropoff_sequence=1, pickup_station_id=station.id,
        dropoff_destination_id=destination.id, fare_total_minor=50_000,
        fare_total_currency="AFN", fare_breakdown=[], status=BookingStatus.CONFIRMED.value,
        verification_code="ABCD", confirmed_at=datetime.now(UTC),
    )
    session.add(booking)
    session.flush()
    seats[0].status = SeatStatus.RESERVED.value
    seats[0].booking_id = booking.id
    session.add(BookingSeatRow(
        id=new_id(), booking_id=booking.id, trip_seat_id=seats[0].id, seat_number=1,
    ))
    session.flush()
    return booking.id, passenger_id


def _cancel(session_factory, booking_id: str, passenger_id: str, barrier) -> str:
    try:
        with UnitOfWork(session_factory) as uow:
            s = uow.session
            use_case = CancelBooking(
                bookings=BookingRepository(s), trips=TripRepository(s),
                seats=TripSeatRepository(s), cancellations=CancellationRepository(s),
                settings=SqlSettingsProvider(s), audit=SqlAuditLog(s, SystemClock()),
                clock=SystemClock(), new_id=new_id, drivers=DriverRepository(s),
            )
            barrier.wait(timeout=10)
            use_case.execute(CancelBookingCommand(
                booking_id=booking_id, actor_id=passenger_id, actor_role=ActorRole.PASSENGER,
            ))
        return "WON"
    except ConflictError as exc:
        return f"LOST:{exc.code}"


@pytest.mark.usefixtures("clean_database")
def test_a_booking_cannot_be_cancelled_twice(engine: Engine, session_factory) -> None:
    with session_factory() as session:
        booking_id, passenger_id = _confirmed_booking(session)
        session.commit()

    results = _race([
        lambda b: _cancel(session_factory, booking_id, passenger_id, b),
        lambda b: _cancel(session_factory, booking_id, passenger_id, b),
    ])
    assert sorted(results) == ["LOST:BOOKING_ALREADY_CANCELLED", "WON"], results

    with session_factory() as session:
        records = session.scalars(
            select(CancellationRow).where(CancellationRow.booking_id == booking_id)
        ).all()
        assert len(records) == 1, "one journey, one cancellation record"
        assert session.get(BookingRow, booking_id).status == BookingStatus.CANCELLED.value
        freed = session.scalars(
            select(TripSeatRow).where(TripSeatRow.status == SeatStatus.AVAILABLE.value)
        ).all()
        assert len(freed) == 4, "the seat went back to the pool, once"


# -- a booking being cancelled by someone with no claim to it ----------------
#
# The only ownership check used to be for passengers: a driver's bearer token
# -- any driver, on any trip -- passed straight through and could cancel a
# booking system-wide, the same way AdvanceTrip's driver check (trip_lifecycle
# .py) stops a driver from advancing a trip that is not theirs.

def _cancel_as(session_factory, booking_id: str, actor_id: str, actor_role: ActorRole) -> None:
    with UnitOfWork(session_factory) as uow:
        s = uow.session
        use_case = CancelBooking(
            bookings=BookingRepository(s), trips=TripRepository(s),
            seats=TripSeatRepository(s), cancellations=CancellationRepository(s),
            settings=SqlSettingsProvider(s), audit=SqlAuditLog(s, SystemClock()),
            clock=SystemClock(), new_id=new_id, drivers=DriverRepository(s),
        )
        use_case.execute(CancelBookingCommand(
            booking_id=booking_id, actor_id=actor_id, actor_role=actor_role,
        ))


@pytest.mark.usefixtures("clean_database")
def test_a_driver_not_on_the_trip_cannot_cancel_its_booking(session_factory) -> None:
    """A driver with no connection to this trip must be refused exactly as a
    stranger would be -- not waved through because the role is DRIVER."""
    with session_factory() as session:
        booking_id, _passenger_id = _confirmed_booking(session)
        _stranger_driver_id, stranger_user_id = _a_driver(session)
        session.commit()

    with pytest.raises(PermissionError):
        _cancel_as(session_factory, booking_id, stranger_user_id, ActorRole.DRIVER)

    with session_factory() as session:
        assert session.get(BookingRow, booking_id).status == BookingStatus.CONFIRMED.value, (
            "a driver with no claim on this trip cancelled it anyway"
        )


@pytest.mark.usefixtures("clean_database")
def test_the_driver_assigned_to_the_trip_can_cancel_its_booking(session_factory) -> None:
    """The new check must not catch the one driver who really is assigned to
    this trip -- whether or not that path is reached from the app today (see
    trip_lifecycle.AdvanceTrip for the driver-cancels-the-whole-trip route),
    the use case itself must keep working for its rightful owner."""
    with session_factory() as session:
        driver_id, driver_user_id = _a_driver(session)
        booking_id, _passenger_id = _confirmed_booking(session, driver_id=driver_id)
        session.commit()

    _cancel_as(session_factory, booking_id, driver_user_id, ActorRole.DRIVER)

    with session_factory() as session:
        assert session.get(BookingRow, booking_id).status == BookingStatus.CANCELLED.value


@pytest.mark.usefixtures("clean_database")
def test_a_driver_can_still_cancel_a_seat_they_booked_as_a_passenger(
    session_factory,
) -> None:
    """A person can hold both roles on the same account, and deps.Actor.role
    (ui/api/deps.py) picks DRIVER over PASSENGER whenever both apply -- so a
    registered driver who also booked a seat on someone else's trip reaches
    this use case with actor_role=DRIVER even though the booking is their own.
    The ownership check must key off whose booking it actually is, not only
    the role label, or a dual-role user is locked out of cancelling their own
    seat unless they happen to also be that trip's assigned driver."""
    with session_factory() as session:
        _own_driver_id, driver_user_id = _a_driver(session)
        booking_id, _ = _confirmed_booking(session, passenger_id=driver_user_id)
        session.commit()

    _cancel_as(session_factory, booking_id, driver_user_id, ActorRole.DRIVER)

    with session_factory() as session:
        assert session.get(BookingRow, booking_id).status == BookingStatus.CANCELLED.value


@pytest.mark.usefixtures("clean_database")
def test_the_passenger_can_still_cancel_their_own_booking(session_factory) -> None:
    """The pre-existing, correct path: unaffected by the added driver check."""
    with session_factory() as session:
        booking_id, passenger_id = _confirmed_booking(session)
        session.commit()

    _cancel_as(session_factory, booking_id, passenger_id, ActorRole.PASSENGER)

    with session_factory() as session:
        assert session.get(BookingRow, booking_id).status == BookingStatus.CANCELLED.value
