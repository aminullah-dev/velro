"""The dashboard as an operations centre, and the board it points at.

A number on a card is a promise: click it and you get exactly those rows.
These hold the card and the list to one definition, and prove the board
carries what a dispatcher acts on -- where a trip leaves from, who is
already on it, whether drivers have been asked, and whether there is
anybody online to ask.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.e2e.conftest import auth, sign_in

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
        everyone = client.get("/api/v1/admin/users", headers=admin_session).json()["meta"]["count"]
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
