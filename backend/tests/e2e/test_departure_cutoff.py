"""Booking after departure, over the real API.

The unit tests next door prove the rule. These prove it is wired: that the
booking endpoint reads the clock, that the operator's cutoff setting reaches
it without a deploy, and that the seat count on the trip is untouched by a
refusal.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.e2e.conftest import auth, sign_in

pytestmark = pytest.mark.integration

RIDER = "+93700000778"


@pytest.fixture(scope="module")
def rider(client: TestClient) -> dict:
    return auth(sign_in(client, RIDER))


def _journey(client: TestClient, headers: dict) -> tuple[str, str, dict]:
    """(origin, destination, first trip option) from the seed."""
    districts = client.get("/api/v1/geo/districts", headers=headers).json()["data"]
    siahgird = next(d for d in districts if d["code"] == "GRB-SYG")
    villages = client.get(
        f"/api/v1/geo/districts/{siahgird['id']}/villages", headers=headers
    ).json()["data"]
    khishki = next(v for v in villages if v["code"] == "GRB-SYG-001")
    station = client.get(
        f"/api/v1/geo/villages/{khishki['id']}/stations", headers=headers
    ).json()["data"][0]
    groups = client.get(
        f"/api/v1/geo/stations/{station['id']}/destinations", headers=headers
    ).json()["data"]
    charikar = next(g for g in groups if g["name"] == "چاریکار")
    options = client.post(
        "/api/v1/trips/search",
        json={"origin_station_id": station["id"], "destination_id": charikar["id"],
              "seat_count": 1},
        headers=headers,
    ).json()["data"]
    assert options, "the seed publishes trips from خیشکی to چاریکار"
    return station["id"], charikar["id"], options[0]


def _book(client, headers, origin, destination, trip_id):
    return client.post(
        "/api/v1/bookings",
        json={"trip_id": trip_id, "seat_count": 1,
              "pickup_station_id": origin, "dropoff_destination_id": destination},
        headers=headers,
    )


def _session():
    from ui.api import deps

    return deps._session_factory()()


class TestATripWhoseTimeHasPassed:
    def test_cannot_be_booked_even_while_still_scheduled(self, client, rider) -> None:
        from infrastructure.db.models.trips import TripRow

        origin, destination, option = _journey(client, rider)
        trip_id = option["trip_id"]
        seats_before = option["seats_available"]

        # Nobody advanced it; the clock simply moved on. Done to the row
        # directly, because nothing in the product can produce this state
        # on purpose -- which is exactly why it has to be refused.
        with _session() as session:
            trip = session.scalars(select(TripRow).where(TripRow.id == trip_id)).one()
            original = trip.scheduled_departure_at
            trip.scheduled_departure_at = datetime.now(UTC) - timedelta(hours=1)
            session.commit()
        try:
            refused = _book(client, rider, origin, destination, trip_id)
            assert refused.status_code == 409, refused.text
            assert refused.json()["error"]["code"] == "TRIP_DEPARTED"
            assert refused.json()["error"]["context"]["status"] == "SCHEDULED", (
                "the status was fine; the clock is what refused it"
            )
        finally:
            with _session() as session:
                trip = session.scalars(select(TripRow).where(TripRow.id == trip_id)).one()
                trip.scheduled_departure_at = original
                session.commit()

        # A refusal touches nothing.
        after = client.post(
            "/api/v1/trips/search",
            json={"origin_station_id": origin, "destination_id": destination,
                  "seat_count": 1},
            headers=rider,
        ).json()["data"]
        assert next(o["seats_available"] for o in after if o["trip_id"] == trip_id) == seats_before


class TestTheOperatorsCutoff:
    def test_is_a_setting_and_takes_effect_at_once(
        self, client, rider, admin_session
    ) -> None:
        """Ten hours before departure closes every trip the seed publishes
        (they leave two to eight hours out); back to zero reopens them."""
        origin, destination, option = _journey(client, rider)

        changed = client.patch(
            "/api/v1/admin/settings/booking.cutoff_minutes",
            json={"value": 600}, headers=admin_session,
        )
        assert changed.status_code == 200, changed.text
        try:
            refused = _book(client, rider, origin, destination, option["trip_id"])
            assert refused.status_code == 409, refused.text
            assert refused.json()["error"]["code"] == "TRIP_DEPARTED"
            assert refused.json()["error"]["context"]["closes_before_minutes"] == 600
        finally:
            restored = client.patch(
                "/api/v1/admin/settings/booking.cutoff_minutes",
                json={"value": 0}, headers=admin_session,
            )
            assert restored.status_code == 200, restored.text

        booked = _book(client, rider, origin, destination, option["trip_id"])
        assert booked.status_code == 200, booked.text
        # Put the seat back for the modules after this one.
        cancelled = client.post(
            f"/api/v1/bookings/{booked.json()['data']['id']}/cancel",
            json={"reason_code": "PASSENGER_CANCELLED"}, headers=rider,
        )
        assert cancelled.status_code == 200, cancelled.text
