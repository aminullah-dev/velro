"""A passenger, seen from the office.

The console could find a driver, a car, a trip and a receipt, and could not
answer the first question a passenger's call raises: who is this, and what
has she done with us. These hold the accounts list to the search, filters
and paging the drivers list already has; the account page to counts taken
from her own rows; the lists behind that page to their passenger; and the
dashboard's passenger card to the definitions it states.

Everything is additive: the same endpoints, gates and shapes with a filter
or a field more, so the panel and the handsets already out there keep
working unchanged.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from tests.e2e.conftest import auth, sign_in

pytestmark = pytest.mark.integration

#: A passenger with a history: bookings in every state, requests, tickets.
SHOPPER = "+93700000890"
#: A passenger who signed up and has done nothing since.
QUIET = "+93700000891"
#: A dispatcher: operations staff, not support.
DESK = "+93700000892"
#: Signs up in the middle of the dashboard test, so every card must move.
NEWCOMER = "+93700000893"
#: A passenger, who may look at none of this.
RIDER = "+93700000894"

SEED_ADMIN = "+93700000001"
SEED_DISPATCHER = "+93700000002"
SEED_DRIVER = "+93700000020"

SHOPPER_NAME = "Shabnam Rahimi"

USERS = "/api/v1/admin/users"
DRIVERS = "/api/v1/admin/drivers"
BOOKINGS = "/api/v1/admin/bookings"
TICKETS = "/api/v1/admin/support/tickets"
REQUESTS = "/api/v1/admin/ride-requests"
DASHBOARD = "/api/v1/admin/dashboard"

NOBODY = "00000000-0000-0000-0000-000000000000"

ROW_FIELDS = {
    "id", "phone", "full_name", "status", "locale", "roles",
    "rating_average", "rating_count", "created_at", "last_seen_at",
}
CARD_FIELDS = {
    "total", "new_today", "new_7d", "active_7d", "active_30d",
    "repeat_30d", "suspended", "with_open_request",
}


def _session():
    from ui.api import deps

    return deps._session_factory()()


def _now() -> datetime:
    from shared.clock import SystemClock

    return SystemClock().now()


def _get(client: TestClient, path: str, headers: dict, **params) -> dict:
    answer = client.get(path, headers=headers, params=params)
    assert answer.status_code == 200, answer.text
    return answer.json()


def _ids(body: dict) -> set[str]:
    return {row["id"] for row in body["data"]}


def _user_id(phone: str) -> str:
    from infrastructure.db.models.identity import UserRow

    with _session() as session:
        return session.scalars(select(UserRow.id).where(UserRow.phone == phone)).one()


def _book(
    session, journey: dict, passenger_id: str, status: str, *,
    seats: int, fare: int, made: datetime, done: datetime | None = None,
) -> None:
    """A booking written directly: what is under test is counting it, and
    the booking rules have their own modules. The stops are never read."""
    from domain.enums import RideKind
    from infrastructure.db.models.trips import BookingRow
    from shared.ids import new_id

    session.add(
        BookingRow(
            id=new_id(), number=f"BKG-T-{new_id()[-12:]}", trip_id=journey["trip_id"],
            passenger_id=passenger_id, ride_kind=RideKind.SHARED.value, seat_count=seats,
            pickup_sequence=0, dropoff_sequence=1,
            pickup_station_id=journey["station_id"],
            dropoff_destination_id=journey["destination_id"],
            fare_total_minor=fare, fare_breakdown=[], status=status,
            verification_code="000000", created_at=made, completed_at=done,
        )
    )


def _ask(session, journey: dict, passenger_id: str, status: str, *, expires_at) -> str:
    from infrastructure.db.models.trips import RideRequestRow
    from shared.ids import new_id

    row = RideRequestRow(
        id=new_id(), passenger_id=passenger_id,
        origin_station_id=journey["station_id"], destination_id=journey["destination_id"],
        passenger_count=1, requested_for=_now(), expires_at=expires_at,
        status=status, offered_fare_minor=50_000,
    )
    session.add(row)
    return row.id


def _close_request(request_id: str) -> None:
    """Off the drivers' boards again: the modules after this one share them."""
    from domain.enums import RideRequestStatus
    from infrastructure.db.models.trips import RideRequestRow

    with _session() as session:
        session.execute(
            update(RideRequestRow)
            .where(RideRequestRow.id == request_id)
            .values(status=RideRequestStatus.CANCELLED.value)
        )
        session.commit()


# -- the people ---------------------------------------------------------------


@pytest.fixture(scope="module")
def journey() -> dict:
    """A trip that belongs to this module alone, for bookings to point at."""
    from domain.enums import RideKind, TripStatus
    from infrastructure.db.models.routing import RouteRow
    from infrastructure.db.models.trips import TripRow, TripSeatRow
    from infrastructure.services.numbers import SqlNumberAllocator
    from shared.ids import new_id

    with _session() as session:
        route = session.scalars(
            select(RouteRow).where(RouteRow.deleted_at.is_(None)).limit(1)
        ).one()
        departure = _now() + timedelta(hours=6)
        trip = TripRow(
            id=new_id(),
            number=SqlNumberAllocator(session).allocate("trip", year=departure.year),
            route_id=route.id, ride_kind=RideKind.SHARED.value, seat_capacity=4,
            scheduled_departure_at=departure, status=TripStatus.SCHEDULED.value,
            origin_station_id=route.origin_station_id, destination_id=route.destination_id,
        )
        session.add(trip)
        session.flush()
        for seat_number in range(1, trip.seat_capacity + 1):
            session.add(TripSeatRow(id=new_id(), trip_id=trip.id, seat_number=seat_number))
        made = {
            "trip_id": trip.id,
            "station_id": route.origin_station_id,
            "destination_id": route.destination_id,
        }
        session.commit()
    return made


@pytest.fixture(scope="module")
def shopper(client: TestClient, admin_session: dict, journey: dict):
    """Five bookings, one in each state that counts differently; three ride
    requests of which one is still open; two tickets, one answered."""
    from domain.enums import BookingStatus as B
    from domain.enums import RideRequestStatus as R
    from infrastructure.db.models.identity import UserRow
    from infrastructure.db.models.ops import SupportTicketRow

    headers = auth(sign_in(client, SHOPPER))
    now = _now()
    first, last = now - timedelta(days=10), now - timedelta(hours=1)
    with _session() as session:
        user = session.scalars(select(UserRow).where(UserRow.phone == SHOPPER)).one()
        user.full_name = SHOPPER_NAME
        user_id = user.id
        for status, seats, fare, made, done in (
            (B.COMPLETED, 1, 15_000, first, now - timedelta(days=2)),
            (B.COMPLETED, 1, 20_000, now - timedelta(days=5), now - timedelta(days=1)),
            (B.CANCELLED, 2, 30_000, now - timedelta(days=3), None),
            (B.NO_SHOW, 1, 10_000, now - timedelta(days=2), None),
            (B.CONFIRMED, 3, 45_000, last, None),
        ):
            _book(
                session, journey, user_id, status.value,
                seats=seats, fare=fare, made=made, done=done,
            )
        open_id = _ask(
            session, journey, user_id, R.OPEN.value, expires_at=now + timedelta(hours=2)
        )
        _ask(session, journey, user_id, R.EXPIRED.value, expires_at=now - timedelta(hours=1))
        _ask(session, journey, user_id, R.CANCELLED.value, expires_at=now + timedelta(hours=2))
        session.commit()

    for body in ("کرایه زیاد بود", "کرایه دوباره زیاد بود"):
        raised = client.post(
            "/api/v1/support/tickets", headers=headers,
            json={"category_code": "FARE_DISPUTE", "body": body},
        )
        assert raised.status_code == 201, raised.text
    with _session() as session:
        tickets = list(
            session.scalars(
                select(SupportTicketRow.id).where(SupportTicketRow.user_id == user_id)
            ).all()
        )
    assert len(tickets) == 2
    answered = client.post(
        f"{TICKETS}/{tickets[0]}/decide", json={"status": "RESOLVED"}, headers=admin_session
    )
    assert answered.status_code == 200, answered.text

    yield {
        "user_id": user_id, "first": first, "last": last,
        "open_request_id": open_id, "tickets": tickets,
    }
    _close_request(open_id)


@pytest.fixture(scope="module")
def quiet(client: TestClient) -> str:
    sign_in(client, QUIET)
    return _user_id(QUIET)


@pytest.fixture(scope="module")
def desk(client: TestClient) -> dict:
    """Open an account the ordinary way, then give it a dispatcher's desk."""
    from infrastructure.db.repositories.identity import UserRepository

    headers = auth(sign_in(client, DESK))
    user_id = _user_id(DESK)
    with _session() as session:
        UserRepository(session).grant_role(user_id, "DISPATCHER")
        session.commit()
    return headers


@pytest.fixture(scope="module")
def rider(client: TestClient) -> dict:
    return auth(sign_in(client, RIDER))


# -- the accounts list ------------------------------------------------------


class TestFindingAnAccount:
    @pytest.mark.parametrize("typed", [
        "0700000890",
        "+93700000890",
        "0093 700 000 890",
        "۰۷۰۰۰۰۰۸۹۰",          # Persian / Pashto keyboard
        "٠٧٠٠٠٠٠٨٩٠",          # Arabic keyboard
    ])
    def test_her_phone_finds_her_however_it_was_typed(
        self, client: TestClient, admin_session: dict, shopper: dict, typed: str
    ) -> None:
        body = _get(client, USERS, admin_session, search=typed)
        assert shopper["user_id"] in _ids(body)
        assert all("700000890" in (u["phone"] or "") for u in body["data"])
        assert body["meta"]["total"] == len(body["data"])

    @pytest.mark.parametrize("typed", ["shabnam", "RAHIMI", "  shabnam   rahimi "])
    def test_her_name_finds_her_in_any_case(
        self, client: TestClient, admin_session: dict, shopper: dict, typed: str
    ) -> None:
        assert shopper["user_id"] in _ids(_get(client, USERS, admin_session, search=typed))

    def test_a_percent_sign_is_a_character_not_a_wildcard(
        self, client: TestClient, admin_session: dict, shopper: dict
    ) -> None:
        body = _get(client, USERS, admin_session, search="%")
        assert body["data"] == []
        assert body["meta"]["total"] == 0

    def test_the_old_phone_filter_still_works(
        self, client: TestClient, admin_session: dict, shopper: dict
    ) -> None:
        body = _get(client, USERS, admin_session, phone="0700000890")
        assert [u["id"] for u in body["data"]] == [shopper["user_id"]]
        assert body["meta"]["count"] == 1

    def test_passengers_are_whoever_holds_the_role(
        self, client: TestClient, admin_session: dict, shopper: dict
    ) -> None:
        body = _get(client, USERS, admin_session, role="PASSENGER", limit=200)
        assert shopper["user_id"] in _ids(body)
        assert all("PASSENGER" in u["roles"] for u in body["data"])
        assert SEED_ADMIN not in {u["phone"] for u in body["data"]}

    def test_staff_is_every_staff_role(
        self, client: TestClient, admin_session: dict, shopper: dict, desk: dict
    ) -> None:
        from domain.identity import STAFF_ROLES

        body = _get(client, USERS, admin_session, role="STAFF", limit=200)
        phones = {u["phone"] for u in body["data"]}
        assert {SEED_ADMIN, SEED_DISPATCHER, DESK} <= phones
        assert SHOPPER not in phones
        assert all(set(u["roles"]) & STAFF_ROLES for u in body["data"])

    def test_drivers_are_whoever_holds_the_role(
        self, client: TestClient, admin_session: dict
    ) -> None:
        body = _get(client, USERS, admin_session, role="DRIVER", limit=200)
        assert SEED_DRIVER in {u["phone"] for u in body["data"]}
        assert all("DRIVER" in u["roles"] for u in body["data"])

    def test_the_filters_combine(
        self, client: TestClient, admin_session: dict, shopper: dict
    ) -> None:
        mine = _get(client, USERS, admin_session, role="PASSENGER", search=SHOPPER)
        assert [u["id"] for u in mine["data"]] == [shopper["user_id"]]
        none = _get(client, USERS, admin_session, role="DRIVER", search=SHOPPER)
        assert none["data"] == [] and none["meta"]["total"] == 0
        off = _get(client, USERS, admin_session, status="SUSPENDED", search=SHOPPER)
        assert off["meta"]["total"] == 0

    def test_an_unknown_role_is_refused(self, client: TestClient, admin_session: dict) -> None:
        answer = client.get(USERS, headers=admin_session, params={"role": "RIDER"})
        assert answer.status_code in (400, 422), answer.text

    def test_the_list_counts_and_pages(
        self, client: TestClient, admin_session: dict, shopper: dict, quiet: str
    ) -> None:
        everyone = _get(client, USERS, admin_session, role="PASSENGER", limit=200)
        total = everyone["meta"]["total"]
        assert total >= 3, "the seed's passenger and this module's two"
        assert total <= 200, "every passenger must fit on the page for this comparison"
        assert everyone["meta"] == {
            "count": len(everyone["data"]), "total": total, "limit": 200, "offset": 0,
        }
        assert len(everyone["data"]) == total

        first = _get(client, USERS, admin_session, role="PASSENGER", limit=1, offset=0)
        second = _get(client, USERS, admin_session, role="PASSENGER", limit=1, offset=1)
        assert second["meta"] == {"count": 1, "total": total, "limit": 1, "offset": 1}
        # Pages stitch together: the order is total, so no row is on two pages.
        assert [first["data"][0]["id"], second["data"][0]["id"]] == [
            u["id"] for u in everyone["data"][:2]
        ]
        past = _get(client, USERS, admin_session, role="PASSENGER", offset=total)
        assert past["data"] == []
        assert past["meta"] == {"count": 0, "total": total, "limit": 50, "offset": total}


# -- one account -------------------------------------------------------------


class TestAnAccountPage:
    def test_the_account_is_the_list_row(
        self, client: TestClient, admin_session: dict, shopper: dict
    ) -> None:
        detail = _get(client, f"{USERS}/{shopper['user_id']}", admin_session)["data"]
        assert set(detail) == {"user", "driver_id", "passenger"}
        listed = _get(client, USERS, admin_session, search=SHOPPER)["data"]
        assert listed == [detail["user"]]
        assert set(detail["user"]) == ROW_FIELDS
        assert detail["user"]["full_name"] == SHOPPER_NAME
        assert detail["user"]["roles"] == ["PASSENGER"]
        assert detail["driver_id"] is None

    def test_every_count_is_taken_from_her_rows(
        self, client: TestClient, admin_session: dict, shopper: dict
    ) -> None:
        history = _get(client, f"{USERS}/{shopper['user_id']}", admin_session)["data"][
            "passenger"
        ]
        assert datetime.fromisoformat(history.pop("first_booking_at")) == shopper["first"]
        assert datetime.fromisoformat(history.pop("last_booking_at")) == shopper["last"]
        assert history == {
            "bookings_total": 5,
            "bookings_completed": 2,
            "bookings_cancelled": 1,
            "no_shows": 1,
            "seats_booked": 6,          # 1 + 1 + 1 + 3: the cancelled two are not
            "spent_minor": 35_000,      # the two completed fares, nothing else
            "currency": "AFN",
            "ride_requests_total": 3,
            "open_ride_requests": 1,
            "tickets_total": 2,
            "tickets_open": 1,
        }

    def test_a_passenger_with_no_history_is_zeros_not_an_error(
        self, client: TestClient, admin_session: dict, quiet: str
    ) -> None:
        body = _get(client, f"{USERS}/{quiet}", admin_session)["data"]
        assert body["driver_id"] is None
        assert body["passenger"] == {
            "bookings_total": 0, "bookings_completed": 0, "bookings_cancelled": 0,
            "no_shows": 0, "seats_booked": 0, "spent_minor": 0, "currency": "AFN",
            "first_booking_at": None, "last_booking_at": None,
            "ride_requests_total": 0, "open_ride_requests": 0,
            "tickets_total": 0, "tickets_open": 0,
        }

    def test_a_driver_names_his_driver_record(
        self, client: TestClient, admin_session: dict
    ) -> None:
        listed = _get(client, DRIVERS, admin_session, search=SEED_DRIVER)["data"]
        driver_id = next(d["id"] for d in listed if d["phone"] == SEED_DRIVER)
        body = _get(client, f"{USERS}/{_user_id(SEED_DRIVER)}", admin_session)["data"]
        assert body["driver_id"] == driver_id
        assert "DRIVER" in body["user"]["roles"]

    def test_an_unknown_account_is_the_suspend_switchs_not_found(
        self, client: TestClient, admin_session: dict
    ) -> None:
        looked = client.get(f"{USERS}/{NOBODY}", headers=admin_session)
        thrown = client.post(f"{USERS}/{NOBODY}/suspend", json={}, headers=admin_session)
        assert looked.status_code == thrown.status_code == 404, looked.text
        assert looked.json()["error"]["code"] == thrown.json()["error"]["code"]
        assert looked.json()["error"]["code"] == "USER_NOT_FOUND"

    def test_a_deleted_account_is_not_found(
        self, client: TestClient, admin_session: dict
    ) -> None:
        from infrastructure.db.models.identity import UserRow
        from shared.ids import new_id

        gone = new_id()
        with _session() as session:
            session.add(UserRow(id=gone, phone=None, full_name="Gone Person", deleted_at=_now()))
            session.commit()
        assert client.get(f"{USERS}/{gone}", headers=admin_session).status_code == 404
        assert gone not in _ids(_get(client, USERS, admin_session, search="Gone Person"))


# -- the lists behind the page ------------------------------------------------


class TestTheListsNameTheirPassenger:
    def test_her_bookings_and_nobody_elses(
        self, client: TestClient, admin_session: dict, shopper: dict
    ) -> None:
        body = _get(client, BOOKINGS, admin_session, passenger_id=shopper["user_id"], limit=200)
        assert body["meta"]["total"] == 5
        assert {b["passenger_id"] for b in body["data"]} == {shopper["user_id"]}
        assert sorted(b["status"] for b in body["data"]) == sorted(
            ["COMPLETED", "COMPLETED", "CANCELLED", "NO_SHOW", "CONFIRMED"]
        )

    def test_every_booking_names_its_passenger(
        self, client: TestClient, admin_session: dict, shopper: dict
    ) -> None:
        rows = _get(client, BOOKINGS, admin_session, limit=200)["data"]
        assert rows
        assert all(isinstance(b["passenger_id"], str) and b["passenger_id"] for b in rows)

    def test_an_unknown_passenger_has_no_bookings(
        self, client: TestClient, admin_session: dict
    ) -> None:
        assert _get(client, BOOKINGS, admin_session, passenger_id=NOBODY)["meta"]["total"] == 0

    def test_her_tickets_name_her(
        self, client: TestClient, admin_session: dict, shopper: dict
    ) -> None:
        data = _get(
            client, TICKETS, admin_session, reporter_id=shopper["user_id"], status="ALL"
        )["data"]
        assert sorted(t["id"] for t in data["tickets"]) == sorted(shopper["tickets"])
        for ticket in data["tickets"]:
            assert ticket["reporter_id"] == shopper["user_id"]
            assert ticket["reporter_name"] == SHOPPER_NAME
            assert ticket["reporter_phone"] == SHOPPER

    def test_without_a_status_it_is_still_the_working_queue(
        self, client: TestClient, admin_session: dict, shopper: dict
    ) -> None:
        data = _get(client, TICKETS, admin_session, reporter_id=shopper["user_id"])["data"]
        assert [t["status"] for t in data["tickets"]] == ["OPEN"]

    def test_every_ticket_names_its_reporter(
        self, client: TestClient, admin_session: dict, shopper: dict
    ) -> None:
        tickets = _get(client, TICKETS, admin_session, status="ALL", limit=200)["data"]["tickets"]
        assert tickets
        assert all(isinstance(t["reporter_id"], str) and t["reporter_id"] for t in tickets)
        assert all({"reporter_name", "reporter_phone"} <= set(t) for t in tickets)

    def test_an_unknown_reporter_has_no_tickets(
        self, client: TestClient, admin_session: dict
    ) -> None:
        data = _get(client, TICKETS, admin_session, reporter_id=NOBODY, status="ALL")["data"]
        assert data["tickets"] == []

    def test_her_open_request_and_nobody_elses(
        self, client: TestClient, admin_session: dict, shopper: dict
    ) -> None:
        rows = _get(client, REQUESTS, admin_session, passenger_id=shopper["user_id"])["data"]
        assert [r["id"] for r in rows] == [shopper["open_request_id"]]
        assert rows[0]["passenger_id"] == shopper["user_id"]
        assert rows[0]["passenger_phone"] == SHOPPER

    def test_every_request_names_its_passenger(
        self, client: TestClient, admin_session: dict, shopper: dict
    ) -> None:
        rows = _get(client, REQUESTS, admin_session)["data"]
        assert rows, "hers at least is open"
        assert all(isinstance(r["passenger_id"], str) and r["passenger_id"] for r in rows)


# -- the dashboard's passenger card -----------------------------------------


class TestThePassengerCard:
    def test_it_is_there_and_adds_up(
        self, client: TestClient, admin_session: dict, shopper: dict
    ) -> None:
        data = _get(client, DASHBOARD, admin_session)["data"]
        card = data["passengers"]
        assert set(card) == CARD_FIELDS
        assert all(isinstance(n, int) and n >= 0 for n in card.values())
        assert card["new_today"] <= card["new_7d"] <= card["total"]
        assert card["active_7d"] <= card["active_30d"] <= card["total"]
        assert card["repeat_30d"] >= 1, "the shopper finished two trips this month"
        assert card["with_open_request"] >= 1, "and is waiting for a third"
        days = data["history"]["days"]
        assert sum(d["new_passengers"] for d in days) == card["new_7d"]
        assert days[-1]["new_passengers"] == card["new_today"]
        # The older, looser count is still there and still counts grants.
        assert data["people"]["passengers"] >= card["total"]

    def test_a_newcomer_moves_every_figure_by_one(
        self, client: TestClient, admin_session: dict, journey: dict
    ) -> None:
        from domain.enums import BookingStatus, RideRequestStatus

        before = _get(client, DASHBOARD, admin_session)["data"]

        sign_in(client, NEWCOMER)
        user_id = _user_id(NEWCOMER)
        now = _now()
        with _session() as session:
            for _ in range(2):
                _book(
                    session, journey, user_id, BookingStatus.COMPLETED.value,
                    seats=1, fare=12_000, made=now, done=now,
                )
            request_id = _ask(
                session, journey, user_id, RideRequestStatus.OPEN.value,
                expires_at=now + timedelta(hours=2),
            )
            session.commit()
        try:
            # He only signs up: registering to drive would grant DRIVER and
            # make him more than a passenger (see TestPassengersOnly).
            thrown = client.post(
                f"{USERS}/{user_id}/suspend", json={"reason": "a test"}, headers=admin_session
            )
            assert thrown.status_code == 200, thrown.text
            after = _get(client, DASHBOARD, admin_session)["data"]
        finally:
            _close_request(request_id)

        moved = {k: after["passengers"][k] - before["passengers"][k] for k in CARD_FIELDS}
        assert moved == dict.fromkeys(CARD_FIELDS, 1)
        today_before, today_after = before["history"]["days"][-1], after["history"]["days"][-1]
        assert today_after["new_passengers"] - today_before["new_passengers"] == 1
        assert today_after["new_drivers"] == today_before["new_drivers"]


# -- passengers and nothing else -----------------------------------------------

#: Signed up as a passenger, then registered to drive: DRIVER at once.
DRIVING = "+93700000897"
#: Signed up as a passenger, then given a desk in finance.
KEEPING_BOOKS = "+93700000898"


@pytest.fixture(scope="module")
def more_than_passengers(client: TestClient, admin_session: dict, journey: dict) -> dict:
    """Two accounts that hold PASSENGER and something more, each doing all
    that would move a passenger figure -- signing up today, finishing two
    trips, waiting for a third, being suspended -- between two readings of
    the dashboard. The Passengers screens must count none of it."""
    from domain.enums import BookingStatus, RideRequestStatus
    from infrastructure.db.models.identity import UserRow
    from infrastructure.db.repositories.identity import UserRepository

    before = _get(client, DASHBOARD, admin_session)["data"]

    driving = auth(sign_in(client, DRIVING))
    registered = client.post("/api/v1/driver/register", json={}, headers=driving)
    assert registered.status_code in (200, 201), registered.text
    sign_in(client, KEEPING_BOOKS)
    ids = {DRIVING: _user_id(DRIVING), KEEPING_BOOKS: _user_id(KEEPING_BOOKS)}

    now = _now()
    waiting: list[str] = []
    with _session() as session:
        UserRepository(session).grant_role(ids[KEEPING_BOOKS], "FINANCE_MANAGER")
        # Suspended as a passenger before he was given his desk. Written
        # directly: the switch refuses a staff account (reason staff_account
        # -- staff lose roles instead), but the row can still be SUSPENDED,
        # and the card must not count it.
        session.get(UserRow, ids[KEEPING_BOOKS]).status = "SUSPENDED"
        for user_id in ids.values():
            for _ in range(2):
                _book(
                    session, journey, user_id, BookingStatus.COMPLETED.value,
                    seats=1, fare=12_000, made=now, done=now,
                )
            waiting.append(
                _ask(
                    session, journey, user_id, RideRequestStatus.OPEN.value,
                    expires_at=now + timedelta(hours=2),
                )
            )
        session.commit()
    try:
        thrown = client.post(
            f"{USERS}/{ids[DRIVING]}/suspend", json={"reason": "a test"}, headers=admin_session
        )
        assert thrown.status_code == 200, thrown.text
        after = _get(client, DASHBOARD, admin_session)["data"]
    finally:
        for request_id in waiting:
            _close_request(request_id)
    return {"ids": set(ids.values()), "driving": ids[DRIVING], "before": before, "after": after}


class TestPassengersOnly:
    def test_role_passenger_still_means_whoever_holds_it(
        self, client: TestClient, admin_session: dict, more_than_passengers: dict,
        shopper: dict,
    ) -> None:
        body = _get(client, USERS, admin_session, role="PASSENGER", limit=200)
        assert more_than_passengers["ids"] <= _ids(body)
        assert shopper["user_id"] in _ids(body)

    def test_passenger_only_leaves_out_drivers_and_staff(
        self, client: TestClient, admin_session: dict, more_than_passengers: dict,
        shopper: dict,
    ) -> None:
        from domain.identity import STAFF_ROLES

        body = _get(
            client, USERS, admin_session, role="PASSENGER", passenger_only="true", limit=200
        )
        assert shopper["user_id"] in _ids(body)
        assert not _ids(body) & more_than_passengers["ids"]
        assert body["meta"]["total"] == len(body["data"])
        for user in body["data"]:
            assert "PASSENGER" in user["roles"]
            assert not set(user["roles"]) & (STAFF_ROLES | {"DRIVER"})

    def test_it_needs_no_role_filter_to_mean_the_same(
        self, client: TestClient, admin_session: dict, more_than_passengers: dict
    ) -> None:
        alone = _get(client, USERS, admin_session, passenger_only="true", limit=200)
        with_role = _get(
            client, USERS, admin_session, role="PASSENGER", passenger_only="true", limit=200
        )
        assert alone == with_role

    def test_it_combines_with_search_status_and_paging(
        self, client: TestClient, admin_session: dict, more_than_passengers: dict,
        shopper: dict, quiet: str,
    ) -> None:
        only = {"passenger_only": "true"}
        assert _get(client, USERS, admin_session, **only, search=DRIVING)["meta"]["total"] == 0
        found = _get(client, USERS, admin_session, **only, search=SHOPPER)
        assert [u["id"] for u in found["data"]] == [shopper["user_id"]]

        off = _get(client, USERS, admin_session, **only, status="SUSPENDED", limit=200)
        assert all(u["status"] == "SUSPENDED" for u in off["data"])
        assert not _ids(off) & more_than_passengers["ids"]

        everyone = _get(client, USERS, admin_session, **only, limit=200)
        total = everyone["meta"]["total"]
        assert total >= 2, "the shopper and the quiet one at least"
        second = _get(client, USERS, admin_session, **only, limit=1, offset=1)
        assert second["meta"] == {"count": 1, "total": total, "limit": 1, "offset": 1}
        assert second["data"][0]["id"] == everyone["data"][1]["id"]

    def test_no_dashboard_figure_counts_them(self, more_than_passengers: dict) -> None:
        before, after = more_than_passengers["before"], more_than_passengers["after"]
        moved = {k: after["passengers"][k] - before["passengers"][k] for k in CARD_FIELDS}
        assert moved == dict.fromkeys(CARD_FIELDS, 0)
        today_before, today_after = before["history"]["days"][-1], after["history"]["days"][-1]
        assert today_after["new_passengers"] == today_before["new_passengers"]
        # new_drivers keeps its meaning: a driver record made that day.
        assert today_after["new_drivers"] - today_before["new_drivers"] == 1
        # The older, looser count still counts every PASSENGER grant.
        assert after["people"]["passengers"] - before["people"]["passengers"] == 2

    def test_the_card_and_the_list_are_one_set(
        self, client: TestClient, admin_session: dict, more_than_passengers: dict
    ) -> None:
        card = _get(client, DASHBOARD, admin_session)["data"]["passengers"]
        listed = _get(client, USERS, admin_session, passenger_only="true", limit=1)
        assert card["total"] == listed["meta"]["total"]
        off = _get(client, USERS, admin_session, passenger_only="true", status="SUSPENDED")
        assert card["suspended"] == off["meta"]["total"]

    def test_his_passenger_page_still_opens(
        self, client: TestClient, admin_session: dict, more_than_passengers: dict
    ) -> None:
        """A driver's booking still links to his account page."""
        user_id = more_than_passengers["driving"]
        body = _get(client, f"{USERS}/{user_id}", admin_session)["data"]
        assert {"DRIVER", "PASSENGER"} <= set(body["user"]["roles"])
        assert body["driver_id"] is not None
        assert body["passenger"]["bookings_completed"] == 2


# -- the gates are the lists' own ----------------------------------------------


_OPERATIONS_READS = [
    (USERS, {"role": "PASSENGER", "search": "0700", "offset": 0}),
    (USERS + "/{shopper}", {}),
    (BOOKINGS, {"passenger_id": "{shopper}"}),
    (REQUESTS, {"passenger_id": "{shopper}"}),
    (DASHBOARD, {}),
]


def _filled(path: str, params: dict, user_id: str) -> tuple[str, dict]:
    return path.format(shopper=user_id), {
        k: v.format(shopper=user_id) if isinstance(v, str) else v for k, v in params.items()
    }


class TestTheGates:
    @pytest.mark.parametrize(
        ("path", "params"),
        [*_OPERATIONS_READS, (TICKETS, {"reporter_id": "{shopper}", "status": "ALL"})],
    )
    def test_a_passenger_may_look_at_none_of_it(
        self, client: TestClient, rider: dict, shopper: dict, path: str, params: dict
    ) -> None:
        path, params = _filled(path, params, shopper["user_id"])
        assert client.get(path, headers=rider, params=params).status_code == 403

    @pytest.mark.parametrize(("path", "params"), _OPERATIONS_READS)
    def test_a_dispatcher_may_look_at_what_operations_may(
        self, client: TestClient, desk: dict, shopper: dict, path: str, params: dict
    ) -> None:
        path, params = _filled(path, params, shopper["user_id"])
        answer = client.get(path, headers=desk, params=params)
        assert answer.status_code == 200, answer.text

    def test_the_ticket_queue_stays_with_support(
        self, client: TestClient, desk: dict, shopper: dict
    ) -> None:
        """A report may describe an assault; a dispatcher is not support, and
        filtering by reporter is still reading the queue."""
        answer = client.get(
            TICKETS, headers=desk, params={"reporter_id": shopper["user_id"], "status": "ALL"}
        )
        assert answer.status_code == 403
