"""The dashboard as an operations centre, and the board it points at.

A number on a card is a promise: click it and you get exactly those rows.
These hold the card and the list to one definition, and prove the board
carries what a dispatcher acts on -- where a trip leaves from, who is
already on it, whether drivers have been asked, and whether there is
anybody online to ask.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from tests.e2e.conftest import auth, sign_in
from ui.api.opscentre import KABUL

pytestmark = pytest.mark.integration

DRIVER = "+93700000021"      # the seed's second driver, نجیب, with the SUV


def _session():
    from ui.api import deps

    return deps._session_factory()()


@pytest.fixture(scope="module")
def dashboard(client: TestClient, admin_session: dict) -> dict:
    answer = client.get("/api/v1/admin/dashboard", headers=admin_session)
    assert answer.status_code == 200, answer.text
    return answer.json()["data"]


class TestTheShapeOfTheScreen:
    def test_answers_the_four_questions(self, dashboard: dict) -> None:
        assert set(dashboard) >= {
            "live", "attention", "today", "capacity", "drivers", "finance", "network", "people",
            "history", "apps",
        }
        assert set(dashboard["live"]) == {
            "on_the_way", "at_the_station", "moving", "departing_soon",
        }
        assert set(dashboard["attention"]) >= {
            "unassigned_trips", "departures_at_risk", "overdue_trips", "open_requests",
            "unanswered_requests", "pending_drivers", "pending_vehicles",
            "pending_documents", "expiring_documents", "open_tickets", "stale_gps_drivers",
        }
        assert set(dashboard["network"]) >= {
            "villages_without_coordinates", "villages_without_stations",
            "stations_without_routes", "routes_without_upcoming_trips",
        }

    def test_passengers_are_passengers_not_everybody(
        self, client: TestClient, admin_session: dict, dashboard: dict
    ) -> None:
        """The old card counted every user row -- drivers, staff, the seed
        admin -- under the word "passengers"."""
        # meta.count is the length of the page, not a total, and the page
        # defaults to fifty: once the suite had signed in fifty-one people
        # this compared the passengers against a truncated list. The largest
        # page, and a check that it really held everybody.
        everyone = client.get(
            "/api/v1/admin/users?limit=200", headers=admin_session
        ).json()["meta"]["count"]
        assert everyone < 200, "every user must fit on the page for this comparison"
        assert dashboard["people"]["passengers"] < everyone
        assert dashboard["people"]["drivers"] == dashboard["drivers"]["total"]


class TestACardIsItsList:
    def test_unassigned_trips(
        self, client: TestClient, admin_session: dict, dashboard: dict
    ) -> None:
        listed = client.get(
            "/api/v1/admin/trips?unassigned=true&limit=200", headers=admin_session
        ).json()
        assert listed["meta"]["total"] == dashboard["attention"]["unassigned_trips"]
        assert all(t["driver_name"] is None for t in listed["data"])

    def test_villages_without_coordinates(
        self, client: TestClient, admin_session: dict, dashboard: dict
    ) -> None:
        listed = client.get(
            "/api/v1/admin/villages?without=coordinates&limit=1", headers=admin_session
        ).json()
        assert listed["meta"]["total"] == dashboard["network"]["villages_without_coordinates"]
        assert all(v["latitude"] is None for v in listed["data"])

    def test_stations_without_routes(
        self, client: TestClient, admin_session: dict, dashboard: dict
    ) -> None:
        listed = client.get(
            "/api/v1/admin/stations?without_routes=true&limit=5", headers=admin_session
        ).json()
        assert listed["meta"]["total"] == dashboard["network"]["stations_without_routes"]
        assert len(listed["data"]) == min(5, listed["meta"]["total"])

    def test_an_overdue_trip_is_counted_and_listed(
        self, client: TestClient, admin_session: dict
    ) -> None:
        """A trip whose time passed with nobody moving it: the case the old
        board could not see, because it only knew about statuses."""
        from infrastructure.db.models.trips import TripRow

        before = client.get("/api/v1/admin/dashboard", headers=admin_session).json()["data"]
        with _session() as session:
            trip = session.scalars(
                select(TripRow).where(
                    TripRow.status == "SCHEDULED", TripRow.driver_id.is_(None)
                ).order_by(TripRow.scheduled_departure_at.desc())
            ).first()
            assert trip is not None
            original = trip.scheduled_departure_at
            trip.scheduled_departure_at = datetime.now(UTC) - timedelta(hours=2)
            session.commit()
            trip_id = trip.id
        try:
            after = client.get("/api/v1/admin/dashboard", headers=admin_session).json()["data"]
            assert after["attention"]["overdue_trips"] == before["attention"]["overdue_trips"] + 1
            listed = client.get(
                "/api/v1/admin/trips?overdue=true&limit=200", headers=admin_session
            ).json()["data"]
            assert trip_id in {t["id"] for t in listed}
            # And it has left the dispatcher's board: past its grace it is a
            # record, not a job.
            board = client.get("/api/v1/dispatch/unassigned", headers=admin_session).json()["data"]
            assert trip_id not in {t["id"] for t in board}
        finally:
            with _session() as session:
                trip = session.get(TripRow, trip_id)
                trip.scheduled_departure_at = original
                session.commit()


@pytest.fixture(scope="module")
def driver(client: TestClient) -> dict:
    session = auth(sign_in(client, DRIVER))
    online = client.post(
        "/api/v1/driver/status", json={"availability": "ONLINE"}, headers=session
    )
    assert online.status_code == 200, online.text
    return session


class TestTheBoard:
    def test_a_row_says_where_who_and_whether_anyone_can_take_it(
        self, client: TestClient, admin_session: dict, driver: dict
    ) -> None:
        answer = client.get("/api/v1/dispatch/unassigned", headers=admin_session)
        assert answer.status_code == 200, answer.text
        rows, meta = answer.json()["data"], answer.json()["meta"]
        assert rows, "the seed leaves today's trips without a driver"
        first = rows[0]
        assert first["origin_station_name"] and first["destination_name"]
        assert first["minutes_to_departure"] > 0
        assert first["booked_seats"] + first["seats_available"] == first["seat_capacity"]
        assert first["candidates"] >= 1, "نجیب is online with a six-seat SUV"
        assert meta["drivers_available"] >= 1
        # Soonest first, always.
        departures = [r["scheduled_departure_at"] for r in rows]
        assert departures == sorted(departures)

    def test_offering_twice_does_not_put_two_cards_on_one_phone(
        self, client: TestClient, admin_session: dict, driver: dict
    ) -> None:
        board = client.get("/api/v1/dispatch/unassigned", headers=admin_session).json()["data"]
        trip = next(r for r in board if r["candidates"] >= 1)

        first = client.post(f"/api/v1/dispatch/trips/{trip['id']}/offer", headers=admin_session)
        assert first.status_code == 200, first.text
        assert first.json()["data"]["offers_made"] >= 1

        # The dispatcher's double tap on a slow connection.
        again = client.post(f"/api/v1/dispatch/trips/{trip['id']}/offer", headers=admin_session)
        assert again.status_code == 200, again.text
        assert again.json()["data"]["offers_made"] == 0

        mine = client.get("/api/v1/driver/offers", headers=driver).json()["data"]
        assert sum(1 for o in mine if o["trip"]["id"] == trip["id"]) == 1

        # And the board knows the offer is out.
        board = client.get("/api/v1/dispatch/unassigned", headers=admin_session).json()["data"]
        row = next(r for r in board if r["id"] == trip["id"])
        assert row["open_offers"] >= 1
        assert row["offers_expire_at"]

    def test_a_driver_with_no_fix_is_counted(
        self, client: TestClient, admin_session: dict, driver: dict
    ) -> None:
        """Online, never pinged: the office cannot place him."""
        snapshot = client.get("/api/v1/admin/dashboard", headers=admin_session).json()["data"]
        assert snapshot["attention"]["stale_gps_drivers"] >= 1
        listed = client.get(
            "/api/v1/admin/drivers?stale_gps=true", headers=admin_session
        ).json()["data"]
        assert any(d["phone"] == DRIVER for d in listed)
        assert all(d["availability"] != "OFFLINE" for d in listed)

        pinged = client.post(
            "/api/v1/driver/location",
            json={"latitude": "35.01", "longitude": "68.55"}, headers=driver,
        )
        assert pinged.status_code == 200, pinged.text
        listed = client.get(
            "/api/v1/admin/drivers?stale_gps=true", headers=admin_session
        ).json()["data"]
        assert not any(d["phone"] == DRIVER for d in listed)
        everyone = client.get("/api/v1/admin/drivers", headers=admin_session).json()["data"]
        me = next(d for d in everyone if d["phone"] == DRIVER)
        assert me["location_age_seconds"] is not None and me["location_age_seconds"] < 60

        # Back offline, as found: the modules after this one share the seed.
        client.post("/api/v1/driver/status", json={"availability": "OFFLINE"}, headers=driver)


# -- the week behind today -------------------------------------------------

DAY_FIELDS = {
    "date", "trips", "bookings", "completed_trips", "cancellations",
    "revenue_minor", "commission_minor",
}


def _bookings_by_day(client: TestClient, admin_session: dict) -> dict[str, int]:
    days = client.get(
        "/api/v1/admin/dashboard", headers=admin_session
    ).json()["data"]["history"]["days"]
    return {d["date"]: d["bookings"] for d in days}


class TestTheWeekBehindToday:
    def test_seven_business_days_oldest_first_ending_today(self, dashboard: dict) -> None:
        history = dashboard["history"]
        assert history["currency"] == "AFN"
        today = datetime.now(KABUL).date()
        assert [date.fromisoformat(d["date"]) for d in history["days"]] == [
            today - timedelta(days=n) for n in range(6, -1, -1)
        ]
        assert all(set(d) == DAY_FIELDS for d in history["days"])

    def test_the_last_bar_is_the_today_cards(self, dashboard: dict) -> None:
        """One definition, grouped differently: if these ever disagree, one
        of the two screens is lying to the operator."""
        last = dashboard["history"]["days"][-1]
        for field in ("trips", "bookings", "completed_trips", "cancellations"):
            assert last[field] == dashboard["today"][field], field
        assert last["revenue_minor"] == dashboard["finance"]["revenue_today_minor"]
        assert last["commission_minor"] == dashboard["finance"]["commission_today_minor"]
        assert last["trips"] > 0, "the seed schedules trips for today"

    def test_a_booking_made_yesterday_in_kabul_lands_on_yesterday(
        self, client: TestClient, admin_session: dict
    ) -> None:
        """02:00 in Kabul is 21:30 the evening before in UTC. Grouped by the
        UTC date, this booking would land two days back."""
        from infrastructure.db.models.identity import UserRow
        from infrastructure.db.models.trips import BookingRow, TripRow
        from shared.ids import new_id

        today = datetime.now(KABUL).date()
        yesterday = today - timedelta(days=1)
        before_that = yesterday - timedelta(days=1)
        at = datetime.combine(yesterday, time(2, 0), tzinfo=KABUL)
        assert at.astimezone(UTC).date() == before_that

        before = _bookings_by_day(client, admin_session)
        with _session() as session:
            trip = session.scalars(
                select(TripRow).where(TripRow.deleted_at.is_(None)).limit(1)
            ).first()
            someone = session.scalars(select(UserRow).limit(1)).first()
            assert trip is not None and someone is not None
            booking = BookingRow(
                id=new_id(), number="BKG-HISTORY-PROBE", trip_id=trip.id,
                passenger_id=someone.id, ride_kind=trip.ride_kind, seat_count=1,
                pickup_sequence=0, dropoff_sequence=1,
                pickup_station_id=trip.origin_station_id,
                dropoff_destination_id=trip.destination_id,
                fare_total_minor=0, fare_breakdown=[], status="CANCELLED",
                verification_code="000000", created_at=at, updated_at=at,
            )
            session.add(booking)
            session.commit()
            booking_id = booking.id
        try:
            after = _bookings_by_day(client, admin_session)
            assert after[yesterday.isoformat()] == before[yesterday.isoformat()] + 1
            assert after[before_that.isoformat()] == before[before_that.isoformat()]
            assert after[today.isoformat()] == before[today.isoformat()]
        finally:
            with _session() as session:
                session.execute(delete(BookingRow).where(BookingRow.id == booking_id))
                session.commit()


# -- the live map ------------------------------------------------------------

LIVE_MAP = "/api/v1/admin/live-map"

#: Drivers written straight into the database, each one a case the map must
#: get right: (phone, name, approval, availability, deleted). Latin names, so
#: the expected order does not hang on the database's collation for Persian.
#: The one on a trip sorts last by name and must still come first.
FLEET = {
    "on_trip": ("+93700000950", "Live Map D", "APPROVED", "ON_TRIP", False),
    "fresh": ("+93700000951", "Live Map A", "APPROVED", "ONLINE", False),
    "stale": ("+93700000952", "Live Map B", "APPROVED", "ONLINE", False),
    "no_fix": ("+93700000953", "Live Map C", "APPROVED", "ONLINE", False),
    "pending": ("+93700000954", "Live Map E", "PENDING", "ONLINE", False),
    "offline": ("+93700000955", "Live Map F", "APPROVED", "OFFLINE", False),
    "deleted": ("+93700000956", "Live Map G", "APPROVED", "ONLINE", True),
}
ON_THE_MAP = ("on_trip", "fresh", "stale", "no_fix")
OFF_THE_MAP = ("pending", "offline", "deleted")
LATITUDE, LONGITUDE = Decimal("35.012345"), Decimal("68.551234")


@pytest.fixture(scope="class")
def fleet(client: TestClient):
    """The drivers above, one car, three positions and a borrowed trip.

    Class-scoped and undone afterwards: the cards earlier in this module are
    held to the seed, and a trip left assigned would move them.
    """
    from infrastructure.db.models.identity import UserRow
    from infrastructure.db.models.supply import DriverLocationRow, DriverRow, VehicleRow
    from infrastructure.db.models.trips import TripRow
    from shared.ids import new_id

    now = datetime.now(UTC)
    ids: dict[str, str] = {}
    with _session() as session:
        users = {key: UserRow(id=new_id(), phone=phone, full_name=name)
                 for key, (phone, name, *_) in FLEET.items()}
        session.add_all(users.values())
        session.flush()
        for key, (_, _, approval, availability, deleted) in FLEET.items():
            driver = DriverRow(
                id=new_id(), user_id=users[key].id, approval_status=approval,
                availability=availability, deleted_at=now if deleted else None,
            )
            session.add(driver)
            ids[key] = driver.id
        session.flush()
        session.add_all([
            VehicleRow(
                id=new_id(), driver_id=ids["on_trip"], vehicle_type_code="SEDAN",
                plate_number="LIVE-0950", plate_key="LIVE0950", seat_capacity=4,
                brand="Toyota", model="Corolla", status="ACTIVE",
            ),
            # A car still waiting for its papers is not a car he can drive.
            VehicleRow(
                id=new_id(), driver_id=ids["fresh"], vehicle_type_code="SEDAN",
                plate_number="LIVE-0951", plate_key="LIVE0951", seat_capacity=4,
                status="PENDING",
            ),
        ])
        for key, age_seconds, heading in (
            ("on_trip", 10, 90), ("fresh", 30, None), ("stale", 3600, 180),
        ):
            session.add(DriverLocationRow(
                id=new_id(), driver_id=ids[key], latitude=LATITUDE, longitude=LONGITUDE,
                heading_degrees=heading, recorded_at=now - timedelta(seconds=age_seconds),
            ))
        trip = session.scalars(
            select(TripRow).where(
                TripRow.status == "SCHEDULED", TripRow.driver_id.is_(None),
                TripRow.deleted_at.is_(None),
            ).order_by(TripRow.scheduled_departure_at.desc())
        ).first()
        assert trip is not None
        trip.driver_id, trip.status = ids["on_trip"], "DRIVER_ASSIGNED"
        trip_id = trip.id
        session.commit()

    yield {**ids, "trip": trip_id}

    with _session() as session:
        trip = session.get(TripRow, trip_id)
        trip.driver_id, trip.status = None, "SCHEDULED"
        session.flush()
        mine = list(ids.values())
        session.execute(delete(DriverLocationRow).where(DriverLocationRow.driver_id.in_(mine)))
        session.execute(delete(VehicleRow).where(VehicleRow.driver_id.in_(mine)))
        session.execute(delete(DriverRow).where(DriverRow.id.in_(mine)))
        session.execute(delete(UserRow).where(UserRow.phone.in_([p for p, *_ in FLEET.values()])))
        session.commit()


def _live_map(client: TestClient, headers: dict) -> dict:
    answer = client.get(LIVE_MAP, headers=headers)
    assert answer.status_code == 200, answer.text
    return answer.json()["data"]


def _by_id(data: dict) -> dict[str, dict]:
    return {d["driver_id"]: d for d in data["drivers"]}


class TestTheLiveMap:
    def test_nobody_signed_in_sees_it(self, client: TestClient) -> None:
        assert client.get(LIVE_MAP).status_code == 401

    def test_a_passenger_does_not_see_it(
        self, client: TestClient, passenger_session: dict
    ) -> None:
        assert client.get(LIVE_MAP, headers=passenger_session).status_code == 403

    def test_the_shape(self, client: TestClient, admin_session: dict, fleet: dict) -> None:
        data = _live_map(client, admin_session)
        assert set(data) == {"generated_at", "stale_after_seconds", "drivers"}
        assert data["stale_after_seconds"] == 300
        for d in data["drivers"]:
            assert set(d) == {
                "driver_id", "name", "phone", "availability", "vehicle", "location",
                "trip", "rehearsing",
            }
            assert d["availability"] in {"ONLINE", "ON_TRIP"}
        on_trip = _by_id(data)[fleet["on_trip"]]
        assert set(on_trip["vehicle"]) == {"plate", "brand", "model"}
        assert set(on_trip["location"]) == {
            "latitude", "longitude", "heading_degrees", "recorded_at", "stale",
        }
        assert set(on_trip["trip"]) == {
            "id", "number", "status", "origin_name", "destination_name",
        }

    def test_only_approved_working_drivers_are_on_it(
        self, client: TestClient, admin_session: dict, fleet: dict
    ) -> None:
        listed = set(_by_id(_live_map(client, admin_session)))
        assert {fleet[k] for k in ON_THE_MAP} <= listed
        assert not {fleet[k] for k in OFF_THE_MAP} & listed

    def test_on_a_trip_first_then_by_name(
        self, client: TestClient, admin_session: dict, fleet: dict
    ) -> None:
        drivers = _live_map(client, admin_session)["drivers"]
        availability = [d["availability"] for d in drivers]
        assert availability == sorted(availability, key=lambda a: a != "ON_TRIP")
        mine = [d["driver_id"] for d in drivers if d["driver_id"] in {fleet[k] for k in ON_THE_MAP}]
        assert mine == [fleet[k] for k in ON_THE_MAP]

    def test_where_he_is_and_whether_that_is_still_true(
        self, client: TestClient, admin_session: dict, fleet: dict
    ) -> None:
        drivers = _by_id(_live_map(client, admin_session))
        fresh = drivers[fleet["fresh"]]["location"]
        assert fresh["latitude"] == pytest.approx(float(LATITUDE))
        assert fresh["longitude"] == pytest.approx(float(LONGITUDE))
        assert fresh["heading_degrees"] is None
        assert fresh["stale"] is False
        assert drivers[fleet["on_trip"]]["location"]["heading_degrees"] == 90
        # An hour-old fix is a position the office must not send anyone to --
        # the same rule the "without a fix" card counts by.
        assert drivers[fleet["stale"]]["location"]["stale"] is True
        assert drivers[fleet["no_fix"]]["location"] is None

    def test_his_car_and_his_trip(
        self, client: TestClient, admin_session: dict, fleet: dict
    ) -> None:
        drivers = _by_id(_live_map(client, admin_session))
        on_trip = drivers[fleet["on_trip"]]
        assert on_trip["name"] == "Live Map D"
        assert on_trip["phone"] == "+93700000950"
        assert on_trip["vehicle"] == {"plate": "LIVE-0950", "brand": "Toyota", "model": "Corolla"}
        assert on_trip["trip"]["id"] == fleet["trip"]
        assert on_trip["trip"]["status"] == "DRIVER_ASSIGNED"
        assert on_trip["trip"]["number"]
        assert on_trip["trip"]["origin_name"] and on_trip["trip"]["destination_name"]
        # A pending car is not his car, and nobody gave him a trip.
        assert drivers[fleet["fresh"]]["vehicle"] is None
        assert drivers[fleet["fresh"]]["trip"] is None

    def test_a_rehearsing_driver_says_so(
        self, client: TestClient, admin_session: dict, fleet: dict,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """App Review's car at a desk in Cupertino must not read as a real
        driver lost somewhere in Ghorband."""
        from ui.api import deps

        real = deps.settings()
        rehearsing = replace(
            real, otp_test_numbers=(*real.otp_test_numbers, FLEET["stale"][0])
        )
        monkeypatch.setattr(deps, "settings", lambda: rehearsing)
        drivers = _by_id(_live_map(client, admin_session))
        assert drivers[fleet["stale"]]["rehearsing"] is True
        assert all(
            drivers[fleet[k]]["rehearsing"] is False for k in ON_THE_MAP if k != "stale"
        )
