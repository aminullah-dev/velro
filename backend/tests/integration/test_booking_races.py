"""The business rules around a booking, under requests that arrive together.

Each rule here was already true in a sequential read of the code, and each
was check-then-act: two callers could both pass the check before either
wrote. ADR 0012's audit covered the seat, the driver and the money; this
covers the rules it did not reach:

  * the limit on active bookings per passenger counted, then inserted -- and
    accepting a fare offer, which is how most rides are booked, did not
    count at all;
  * one open ride request per passenger was a lookup followed by an insert;
  * a driver withdrawing an offer and a passenger accepting it both wrote
    the offer's status, and the last writer won -- a trip could be built on
    a withdrawn offer;
  * boarding read the booking unlocked, so a cancellation committing in the
    same instant was overwritten with ONBOARD;
  * a rating added to the ratee's running total in Python, so two ratings
    together kept one, and a double tap died on the unique constraint as a
    500 instead of "already rated".

Real threads, real connections, a real PostgreSQL. Where the outcome depends
on both callers having read before either writes, a barrier holds each one
just after the read that used to decide it. With a fix in place a lock may
keep the second caller from ever reaching that point; the barrier then times
out for the first, which carries on, and the test proves the second waited.
"""

from __future__ import annotations

import contextlib
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from application.use_cases.book_seats import BookSeats, BookSeatsCommand
from application.use_cases.cancel_booking import CancelBooking, CancelBookingCommand
from application.use_cases.negotiate_fare import (
    AcceptOffer,
    AcceptOfferCommand,
    RequestRide,
    RequestRideCommand,
    WithdrawOffer,
    WithdrawOfferCommand,
)
from application.use_cases.rate_trip import RateTrip, RateTripCommand
from application.use_cases.trip_lifecycle import VerifyPassenger, VerifyPassengerCommand
from domain.enums import (
    ActorRole,
    BookingStatus,
    FareOfferStatus,
    RideKind,
    RideRequestStatus,
    TripStatus,
)
from domain.fare import FareComponent, FareQuote
from infrastructure.db.models.ops import CancellationRow, RatingRow
from infrastructure.db.models.routing import RouteStopRow
from infrastructure.db.models.supply import DriverRow
from infrastructure.db.models.trips import (
    BookingRow,
    FareOfferRow,
    RideRequestRow,
    TripRow,
    TripSeatRow,
)
from infrastructure.db.repositories.geography import GeographyRepository
from infrastructure.db.repositories.identity import UserRepository
from infrastructure.db.repositories.ops import CancellationRepository, RatingRepository
from infrastructure.db.repositories.routing import RouteRepository
from infrastructure.db.repositories.seats import TripSeatRepository
from infrastructure.db.repositories.supply import DriverRepository, VehicleRepository
from infrastructure.db.repositories.trips import (
    BookingRepository,
    FareOfferRepository,
    RideRequestRepository,
    TripRepository,
)
from infrastructure.db.session import UnitOfWork
from infrastructure.services.audit import SqlAuditLog
from infrastructure.services.codes import SecretsVerificationCodeGenerator
from infrastructure.services.numbers import SqlNumberAllocator
from infrastructure.services.settings import SqlSettingsProvider
from shared.clock import SystemClock
from shared.errors import AppError
from shared.ids import new_id
from shared.money import Money
from tests.integration.test_driver_assignment_concurrency import (
    _person,
    _places,
    _road_ready_driver,
    _scheduled_trip,
    _sequences,
)

pytestmark = pytest.mark.integration

#: The default in infrastructure/services/settings.py.
MAX_ACTIVE = 5
CODE = "K7M2Q9"


# -- holding callers at the old race point --------------------------------

def _hold_after(monkeypatch, cls, methods: tuple[str, ...], barrier, timeout: float) -> None:
    """Every caller of cls.<method> waits for the others just after the read.

    One barrier may be shared across classes, so two different use cases can
    be lined up at their own read. A caller whose rival is stuck behind a lock
    waits ``timeout`` and goes on; that is the fix working, not a hang.
    """
    for method in methods:
        if not hasattr(cls, method):
            continue
        original = getattr(cls, method)

        def held(self, *args, _original=original, **kwargs):
            result = _original(self, *args, **kwargs)
            with contextlib.suppress(threading.BrokenBarrierError):
                barrier.wait(timeout)
            return result

        monkeypatch.setattr(cls, method, held)


def _outcome(call) -> str:
    try:
        call()
        return "WON"
    except AppError as exc:
        return f"LOST:{exc.code}"
    except Exception as exc:  # the 500s these tests exist to remove
        return f"ERROR:{type(exc).__name__}"


def _together(*calls) -> list[str]:
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(_outcome, calls))


# -- the use cases, one transaction each -----------------------------------

class _FlatFare:
    """BookSeats prices through a strategy; the price is not under test."""

    def quote(self, request) -> FareQuote:
        return FareQuote(
            components=(
                FareComponent(key="fare.component.base", amount=Money(50_000, "AFN")),
            ),
            currency="AFN",
            ride_kind=request.ride_kind,
            seat_count=request.seat_count,
            route_id=request.route_id,
            from_sequence=request.from_sequence,
            to_sequence=request.to_sequence,
        )


def _book(session_factory, trip_id: str, passenger_id: str, places: dict) -> None:
    with UnitOfWork(session_factory) as uow:
        s = uow.session
        BookSeats(
            trips=TripRepository(s), seats=TripSeatRepository(s),
            bookings=BookingRepository(s), routes=RouteRepository(s),
            fare_strategy=_FlatFare(), numbers=SqlNumberAllocator(s),
            codes=SecretsVerificationCodeGenerator(), settings=SqlSettingsProvider(s),
            audit=SqlAuditLog(s, SystemClock()), clock=SystemClock(), new_id=new_id,
        ).execute(
            BookSeatsCommand(
                trip_id=trip_id, passenger_id=passenger_id, seat_count=1,
                pickup_station_id=places["station_id"],
                dropoff_destination_id=places["destination_id"],
            )
        )


def _accept(session_factory, offer_id: str, passenger_id: str) -> None:
    with UnitOfWork(session_factory) as uow:
        s = uow.session
        AcceptOffer(
            requests=RideRequestRepository(s), offers=FareOfferRepository(s),
            trips=TripRepository(s), bookings=BookingRepository(s),
            seats=TripSeatRepository(s), drivers=DriverRepository(s),
            vehicles=VehicleRepository(s), routes=RouteRepository(s),
            geography=GeographyRepository(s), numbers=SqlNumberAllocator(s),
            codes=SecretsVerificationCodeGenerator(),
            audit=SqlAuditLog(s, SystemClock()), clock=SystemClock(), new_id=new_id,
        ).execute(AcceptOfferCommand(offer_id=offer_id, passenger_id=passenger_id))


def _withdraw(session_factory, offer_id: str, driver_user_id: str) -> None:
    with UnitOfWork(session_factory) as uow:
        s = uow.session
        WithdrawOffer(
            offers=FareOfferRepository(s), drivers=DriverRepository(s),
            audit=SqlAuditLog(s, SystemClock()), clock=SystemClock(),
        ).execute(WithdrawOfferCommand(offer_id=offer_id, driver_user_id=driver_user_id))


def _ask(session_factory, passenger_id: str, places: dict) -> None:
    with UnitOfWork(session_factory) as uow:
        s = uow.session
        RequestRide(
            requests=RideRequestRepository(s), geography=GeographyRepository(s),
            settings=SqlSettingsProvider(s), audit=SqlAuditLog(s, SystemClock()),
            clock=SystemClock(), new_id=new_id,
        ).execute(
            RequestRideCommand(
                passenger_id=passenger_id, origin_station_id=places["station_id"],
                destination_id=places["destination_id"], passenger_count=1,
                offered_fare_minor=90_000,
            )
        )


def _verify(session_factory, trip_id: str, driver_user_id: str) -> None:
    with UnitOfWork(session_factory) as uow:
        s = uow.session
        VerifyPassenger(
            trips=TripRepository(s), bookings=BookingRepository(s),
            drivers=DriverRepository(s), seats=TripSeatRepository(s),
            users=UserRepository(s), audit=SqlAuditLog(s, SystemClock()),
            clock=SystemClock(), settings=SqlSettingsProvider(s),
        ).execute(
            VerifyPassengerCommand(
                trip_id=trip_id, presented_code=CODE, driver_user_id=driver_user_id
            )
        )


def _cancel(session_factory, booking_id: str, passenger_id: str) -> None:
    with UnitOfWork(session_factory) as uow:
        s = uow.session
        CancelBooking(
            bookings=BookingRepository(s), trips=TripRepository(s),
            seats=TripSeatRepository(s), cancellations=CancellationRepository(s),
            settings=SqlSettingsProvider(s), audit=SqlAuditLog(s, SystemClock()),
            clock=SystemClock(), new_id=new_id, drivers=DriverRepository(s),
        ).execute(
            CancelBookingCommand(
                booking_id=booking_id, actor_id=passenger_id,
                actor_role=ActorRole.PASSENGER,
            )
        )


def _rate(session_factory, trip_id: str, rater_user_id: str, score: int) -> None:
    with UnitOfWork(session_factory) as uow:
        s = uow.session
        RateTrip(
            trips=TripRepository(s), bookings=BookingRepository(s),
            drivers=DriverRepository(s), ratings=RatingRepository(s),
            users=UserRepository(s), audit=SqlAuditLog(s, SystemClock()),
            clock=SystemClock(), new_id=new_id,
        ).execute(RateTripCommand(trip_id=trip_id, rater_user_id=rater_user_id, score=score))


# -- building the world ------------------------------------------------------

def _bookable(session) -> dict:
    """A station, a destination, the route between them with its two stops."""
    places = _places(session)
    session.add_all([
        RouteStopRow(
            id=new_id(), route_id=places["route_id"], sequence=0,
            station_id=places["station_id"], is_pickup=True, is_dropoff=False,
        ),
        RouteStopRow(
            id=new_id(), route_id=places["route_id"], sequence=1,
            destination_id=places["destination_id"], is_pickup=False, is_dropoff=True,
        ),
    ])
    session.flush()
    _sequences(session)
    return places


def _booking(
    session, places: dict, trip_id: str, passenger_id: str,
    *, status: BookingStatus = BookingStatus.CONFIRMED, code: str | None = None,
) -> str:
    booking_id = new_id()
    session.add(
        BookingRow(
            id=booking_id, number=f"BKG-2026-{booking_id[-12:]}", trip_id=trip_id,
            passenger_id=passenger_id, ride_kind=RideKind.SHARED.value, seat_count=1,
            pickup_sequence=0, dropoff_sequence=1,
            pickup_station_id=places["station_id"],
            dropoff_destination_id=places["destination_id"],
            fare_total_minor=50_000, fare_total_currency="AFN",
            fare_breakdown=[{"key": "fare.component.base", "amount_minor": 50_000}],
            status=status.value, verification_code=code or booking_id[-6:].upper(),
        )
    )
    session.flush()
    return booking_id


def _offer_on_open_request(session, places: dict, passenger_id: str, driver_id: str) -> str:
    now = datetime.now(UTC)
    request = RideRequestRow(
        id=new_id(), passenger_id=passenger_id,
        origin_station_id=places["station_id"], destination_id=places["destination_id"],
        passenger_count=1, requested_for=now + timedelta(hours=2),
        expires_at=now + timedelta(hours=1), status=RideRequestStatus.OPEN.value,
        offered_fare_minor=90_000, offered_fare_currency="AFN",
    )
    session.add(request)
    session.flush()
    offer = FareOfferRow(
        id=new_id(), ride_request_id=request.id, driver_id=driver_id,
        amount_minor=95_000, amount_currency="AFN", status=FareOfferStatus.OFFERED.value,
    )
    session.add(offer)
    session.flush()
    return offer.id


def _active_bookings(session_factory, passenger_id: str) -> int:
    with session_factory() as session:
        return session.scalar(
            select(func.count()).select_from(BookingRow).where(
                BookingRow.passenger_id == passenger_id,
                BookingRow.status.not_in(
                    [BookingStatus.CANCELLED.value, BookingStatus.COMPLETED.value,
                     BookingStatus.NO_SHOW.value]
                ),
            )
        )


# -- 1. the limit on active bookings -----------------------------------------

@pytest.mark.usefixtures("clean_database")
class TestTheActiveBookingLimit:
    def _passenger_one_short(self, session_factory) -> tuple[dict, str, str, str]:
        """A passenger with one booking left, a trip with seats, a driver's bid."""
        with session_factory() as session:
            places = _bookable(session)
            passenger_id = _person(session, "احمد")
            elsewhere = _scheduled_trip(session, places)
            for _ in range(MAX_ACTIVE - 1):
                _booking(session, places, elsewhere, passenger_id)
            trip_id = _scheduled_trip(session, places)
            _, driver_id = _road_ready_driver(session, "محمد", "PRW-1111")
            offer_id = _offer_on_open_request(session, places, passenger_id, driver_id)
            session.commit()
        return places, passenger_id, trip_id, offer_id

    def test_accepting_an_offer_counts_against_the_limit(self, session_factory) -> None:
        # The negotiated path is how rides are actually booked, and it never
        # looked at the limit: a passenger at the maximum could keep hiring.
        with session_factory() as session:
            places = _bookable(session)
            passenger_id = _person(session, "احمد")
            trip_id = _scheduled_trip(session, places)
            for _ in range(MAX_ACTIVE):
                _booking(session, places, trip_id, passenger_id)
            _, driver_id = _road_ready_driver(session, "محمد", "PRW-1111")
            offer_id = _offer_on_open_request(session, places, passenger_id, driver_id)
            session.commit()

        assert _outcome(lambda: _accept(session_factory, offer_id, passenger_id)) == (
            "LOST:BOOKING_LIMIT_REACHED"
        )
        assert _active_bookings(session_factory, passenger_id) == MAX_ACTIVE
        with session_factory() as session:
            assert session.get(FareOfferRow, offer_id).status == FareOfferStatus.OFFERED.value

    def test_two_bookings_at_once_cannot_pass_the_last_place(
        self, session_factory, monkeypatch
    ) -> None:
        places, passenger_id, trip_id, _ = self._passenger_one_short(session_factory)

        barrier = threading.Barrier(2)
        _hold_after(
            monkeypatch, BookingRepository, ("count_active_for_passenger",), barrier, 3
        )
        results = _together(
            lambda: _book(session_factory, trip_id, passenger_id, places),
            lambda: _book(session_factory, trip_id, passenger_id, places),
        )
        monkeypatch.undo()

        assert sorted(results) == ["LOST:BOOKING_LIMIT_REACHED", "WON"], results
        assert _active_bookings(session_factory, passenger_id) == MAX_ACTIVE

    def test_a_booking_and_an_accept_at_once_cannot_pass_it_either(
        self, session_factory, monkeypatch
    ) -> None:
        places, passenger_id, trip_id, offer_id = self._passenger_one_short(session_factory)

        barrier = threading.Barrier(2)
        _hold_after(
            monkeypatch, BookingRepository, ("count_active_for_passenger",), barrier, 3
        )
        results = _together(
            lambda: _book(session_factory, trip_id, passenger_id, places),
            lambda: _accept(session_factory, offer_id, passenger_id),
        )
        monkeypatch.undo()

        assert sorted(results) == ["LOST:BOOKING_LIMIT_REACHED", "WON"], results
        assert _active_bookings(session_factory, passenger_id) == MAX_ACTIVE


# -- 2. one open request per passenger ------------------------------------------

@pytest.mark.usefixtures("clean_database")
class TestOneOpenRequest:
    def test_two_asks_at_once_leave_one_open_request(
        self, session_factory, monkeypatch
    ) -> None:
        with session_factory() as session:
            places = _bookable(session)
            passenger_id = _person(session, "زهرا")
            session.commit()

        barrier = threading.Barrier(2)
        _hold_after(
            monkeypatch, RideRequestRepository, ("find_open_for_passenger",), barrier, 3
        )
        results = _together(
            lambda: _ask(session_factory, passenger_id, places),
            lambda: _ask(session_factory, passenger_id, places),
        )
        monkeypatch.undo()

        # The loser hears the domain answer -- with the winner's id, so the
        # app can open it -- not a 500 from the unique index.
        assert sorted(results) == ["LOST:RIDE_REQUEST_ALREADY_OPEN", "WON"], results
        with session_factory() as session:
            open_rows = session.scalars(
                select(RideRequestRow).where(
                    RideRequestRow.passenger_id == passenger_id,
                    RideRequestRow.status == RideRequestStatus.OPEN.value,
                )
            ).all()
        assert len(open_rows) == 1

    def test_the_loser_is_told_which_request_is_open(
        self, session_factory, monkeypatch
    ) -> None:
        with session_factory() as session:
            places = _bookable(session)
            passenger_id = _person(session, "زهرا")
            session.commit()

        barrier = threading.Barrier(2)
        _hold_after(
            monkeypatch, RideRequestRepository, ("find_open_for_passenger",), barrier, 3
        )
        errors: list[AppError] = []

        def ask() -> None:
            try:
                _ask(session_factory, passenger_id, places)
            except AppError as exc:
                errors.append(exc)

        _together(ask, ask)
        monkeypatch.undo()

        assert len(errors) == 1, errors
        with session_factory() as session:
            winner = session.scalars(
                select(RideRequestRow).where(RideRequestRow.passenger_id == passenger_id)
            ).one()
        assert errors[0].code == "RIDE_REQUEST_ALREADY_OPEN"
        assert errors[0].context["ride_request_id"] == winner.id

    def test_a_request_past_its_deadline_does_not_hold_the_place(
        self, session_factory
    ) -> None:
        # Still OPEN in the row because nobody has looked at it since it ran
        # out of time. Readers already ignore it; the index must not count it.
        now = datetime.now(UTC)
        with session_factory() as session:
            places = _bookable(session)
            passenger_id = _person(session, "زهرا")
            stale = RideRequestRow(
                id=new_id(), passenger_id=passenger_id,
                origin_station_id=places["station_id"],
                destination_id=places["destination_id"], passenger_count=1,
                requested_for=now - timedelta(hours=2), expires_at=now - timedelta(hours=1),
                status=RideRequestStatus.OPEN.value, offered_fare_minor=90_000,
                offered_fare_currency="AFN",
            )
            session.add(stale)
            session.commit()
            stale_id = stale.id

        assert _outcome(lambda: _ask(session_factory, passenger_id, places)) == "WON"
        with session_factory() as session:
            assert session.get(RideRequestRow, stale_id).status == (
                RideRequestStatus.EXPIRED.value
            )


# -- 3. withdrawing an offer while it is being accepted ---------------------

@pytest.mark.usefixtures("clean_database")
def test_withdraw_and_accept_cannot_both_win(session_factory, monkeypatch) -> None:
    with session_factory() as session:
        places = _bookable(session)
        passenger_id = _person(session, "احمد")
        driver_user_id, driver_id = _road_ready_driver(session, "محمد", "PRW-1111")
        offer_id = _offer_on_open_request(session, places, passenger_id, driver_id)
        session.commit()

    barrier = threading.Barrier(2)
    _hold_after(monkeypatch, FareOfferRepository, ("find",), barrier, 3)
    results = _together(
        lambda: _accept(session_factory, offer_id, passenger_id),
        lambda: _withdraw(session_factory, offer_id, driver_user_id),
    )
    monkeypatch.undo()

    assert sorted(results) == ["LOST:FARE_OFFER_NOT_OPEN", "WON"], results
    accept_won = results[0] == "WON"
    with session_factory() as session:
        offer = session.get(FareOfferRow, offer_id)
        request = session.get(RideRequestRow, offer.ride_request_id)
        trips = session.scalars(select(TripRow).where(TripRow.driver_id == driver_id)).all()
        if accept_won:
            assert offer.status == FareOfferStatus.ACCEPTED.value
            assert request.status == RideRequestStatus.MATCHED.value
            assert len(trips) == 1
        else:
            # Withdrawn means withdrawn: no trip was built on it.
            assert offer.status == FareOfferStatus.WITHDRAWN.value
            assert request.status == RideRequestStatus.OPEN.value
            assert trips == []


@pytest.mark.usefixtures("clean_database")
def test_an_accepted_offer_cannot_be_withdrawn(session_factory) -> None:
    with session_factory() as session:
        places = _bookable(session)
        passenger_id = _person(session, "احمد")
        driver_user_id, driver_id = _road_ready_driver(session, "محمد", "PRW-1111")
        offer_id = _offer_on_open_request(session, places, passenger_id, driver_id)
        session.commit()

    assert _outcome(lambda: _accept(session_factory, offer_id, passenger_id)) == "WON"
    assert _outcome(lambda: _withdraw(session_factory, offer_id, driver_user_id)) == (
        "LOST:FARE_OFFER_NOT_OPEN"
    )
    with session_factory() as session:
        assert session.get(FareOfferRow, offer_id).status == FareOfferStatus.ACCEPTED.value


# -- 4. boarding a passenger while the booking is being cancelled --------------

@pytest.mark.usefixtures("clean_database")
def test_boarding_and_cancelling_cannot_both_win(session_factory, monkeypatch) -> None:
    with session_factory() as session:
        places = _bookable(session)
        passenger_id = _person(session, "احمد")
        driver_user_id, driver_id = _road_ready_driver(session, "محمد", "PRW-1111")
        trip_id = _scheduled_trip(session, places)
        trip = session.get(TripRow, trip_id)
        trip.status = TripStatus.ARRIVED_AT_PICKUP.value
        trip.driver_id = driver_id
        booking_id = _booking(
            session, places, trip_id, passenger_id, status=BookingStatus.READY, code=CODE
        )
        seats = TripSeatRepository(session)
        seats.reserve(seats.lock_available(trip_id, 1), booking_id)
        session.commit()

    barrier = threading.Barrier(2)
    _hold_after(
        monkeypatch, BookingRepository,
        ("find_by_verification_code", "lock_by_verification_code", "lock"), barrier, 3,
    )
    results = _together(
        lambda: _verify(session_factory, trip_id, driver_user_id),
        lambda: _cancel(session_factory, booking_id, passenger_id),
    )
    monkeypatch.undo()

    boarded, cancelled = results
    assert sorted(results) in (
        # Boarded first: an aboard passenger is past cancelling.
        ["LOST:BOOKING_NOT_CANCELLABLE", "WON"],
        # Cancelled first: the code now matches no live booking, which is
        # exactly what the driver would hear a second later.
        ["LOST:BOOKING_VERIFICATION_FAILED", "WON"],
    ), results
    with session_factory() as session:
        booking = session.get(BookingRow, booking_id)
        records = session.scalars(
            select(CancellationRow).where(CancellationRow.booking_id == booking_id)
        ).all()
        seat = session.scalars(select(TripSeatRow).where(TripSeatRow.trip_id == trip_id)).first()
        if boarded == "WON":
            assert booking.status == BookingStatus.ONBOARD.value
            assert records == []
        else:
            assert cancelled == "WON"
            assert booking.status == BookingStatus.CANCELLED.value
            assert len(records) == 1
            assert seat.booking_id is None


# -- 5. ratings ------------------------------------------------------------------

def _completed_trip_with(session_factory, riders: int) -> tuple[str, str, list[str]]:
    with session_factory() as session:
        places = _bookable(session)
        _, driver_id = _road_ready_driver(session, "محمد", "PRW-1111")
        trip_id = _scheduled_trip(session, places)
        trip = session.get(TripRow, trip_id)
        trip.status = TripStatus.COMPLETED.value
        trip.driver_id = driver_id
        passengers = [_person(session, f"مسافر {n}") for n in range(riders)]
        for passenger_id in passengers:
            _booking(session, places, trip_id, passenger_id, status=BookingStatus.COMPLETED)
        session.commit()
    return trip_id, driver_id, passengers


@pytest.mark.usefixtures("clean_database")
def test_two_ratings_at_once_both_count(session_factory, monkeypatch) -> None:
    trip_id, driver_id, (first, second) = _completed_trip_with(session_factory, 2)

    barrier = threading.Barrier(2)
    _hold_after(monkeypatch, RatingRepository, ("find",), barrier, 3)
    results = _together(
        lambda: _rate(session_factory, trip_id, first, 5),
        lambda: _rate(session_factory, trip_id, second, 3),
    )
    monkeypatch.undo()

    assert results == ["WON", "WON"], results
    with session_factory() as session:
        driver = session.get(DriverRow, driver_id)
        assert (driver.rating_count, driver.rating_sum) == (2, 8), (
            "a score was lost: the total was read before the other rating "
            "committed and written back over it"
        )


@pytest.mark.usefixtures("clean_database")
def test_a_double_tap_on_a_rating_is_a_conflict_not_a_crash(
    session_factory, monkeypatch
) -> None:
    trip_id, driver_id, (passenger_id,) = _completed_trip_with(session_factory, 1)

    barrier = threading.Barrier(2)
    _hold_after(monkeypatch, RatingRepository, ("find",), barrier, 3)
    results = _together(
        lambda: _rate(session_factory, trip_id, passenger_id, 4),
        lambda: _rate(session_factory, trip_id, passenger_id, 4),
    )
    monkeypatch.undo()

    assert sorted(results) == ["LOST:RATING_ALREADY_SUBMITTED", "WON"], results
    with session_factory() as session:
        driver = session.get(DriverRow, driver_id)
        assert (driver.rating_count, driver.rating_sum) == (1, 4)
        assert session.scalar(
            select(func.count()).select_from(RatingRow).where(RatingRow.trip_id == trip_id)
        ) == 1
