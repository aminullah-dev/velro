"""The fence, proven through the front door.

Every other module in this suite runs on personas the conftest exempts --
which is itself half the proof: their asks and bookings carry no coordinates
at all, and they pass only because exemption works. This module signs in the
one number the exemption list deliberately omits and walks it into the fence
from both sides.

Herat is the stand-in for "some other province with a spare SIM": ~570 km
from the nearest seeded station. خیشکی in Ghorband is the inside probe,
using its exact seeded coordinates.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import auth, sign_in

#: Deliberately absent from VELRO_GEOFENCE_EXEMPT_PHONES in conftest.
FENCED_PHONE = "+93700000555"

INSIDE = {"latitude": "35.1250", "longitude": "68.7700"}   # خیشکی itself
HERAT = {"latitude": "34.35", "longitude": "62.20"}


# Once per module: a second OTP inside the cooldown is refused, which is the
# limiter doing its job, not an inconvenience to code around.
@pytest.fixture(scope="module")
def fenced_rider(client: TestClient) -> dict:
    return auth(sign_in(client, FENCED_PHONE))


def _journeys(client: TestClient, headers: dict):
    for district in client.get("/api/v1/geo/districts", headers=headers).json()["data"]:
        for village in client.get(
            f"/api/v1/geo/districts/{district['id']}/villages", headers=headers
        ).json()["data"]:
            for station in client.get(
                f"/api/v1/geo/villages/{village['id']}/stations", headers=headers
            ).json()["data"]:
                for group in client.get(
                    f"/api/v1/geo/stations/{station['id']}/destinations", headers=headers
                ).json()["data"]:
                    for target in (group.get("children") or [group]):
                        yield station["id"], target["id"]


def _first_journey(client: TestClient, headers: dict) -> tuple[str, str]:
    for pair in _journeys(client, headers):
        return pair
    raise AssertionError("seed has no journeys")


def _ask(client: TestClient, headers: dict, journey: tuple[str, str], **coords):
    origin, destination = journey
    return client.post(
        "/api/v1/ride-requests",
        json={
            "origin_station_id": origin,
            "destination_id": destination,
            "passenger_count": 1,
            "offered_fare_minor": 50_000,
            **coords,
        },
        headers=headers,
    )


class TestAskFence:
    def test_herat_cannot_ring_the_drivers(self, client: TestClient, fenced_rider: dict):
        rider = fenced_rider
        refused = _ask(client, rider, _first_journey(client, rider), **HERAT)
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "GEOFENCE_OUTSIDE"

    def test_no_location_is_refused_not_waved_through(self, client: TestClient, fenced_rider: dict):
        rider = fenced_rider
        refused = _ask(client, rider, _first_journey(client, rider))
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "GEOFENCE_OUTSIDE"

    def test_standing_at_the_station_is_let_through(self, client: TestClient, fenced_rider: dict):
        rider = fenced_rider
        allowed = _ask(client, rider, _first_journey(client, rider), **INSIDE)
        assert allowed.status_code == 201, allowed.text
        # Leave no open request behind for other modules to trip over.
        done = client.post(
            f"/api/v1/ride-requests/{allowed.json()['data']['id']}/cancel",
            headers=rider,
        )
        assert done.status_code == 200, done.text


class TestBookingFence:
    def test_herat_cannot_take_a_seat_either(self, client: TestClient, fenced_rider: dict):
        rider = fenced_rider
        # Not every pair has a scheduled trip; walk until one does, the way
        # the concurrency module does.
        origin = destination = None
        options = []
        for origin, destination in _journeys(client, rider):
            options = client.post(
                "/api/v1/trips/search",
                json={
                    "origin_station_id": origin,
                    "destination_id": destination,
                    "seat_count": 1,
                },
                headers=rider,
            ).json()["data"]
            if options:
                break
        assert options, "seed must offer at least one bookable option"
        refused = client.post(
            "/api/v1/bookings",
            json={
                "trip_id": options[0]["trip_id"],
                "seat_count": 1,
                "pickup_station_id": origin,
                "dropoff_destination_id": destination,
                **HERAT,
            },
            headers=rider,
        )
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "GEOFENCE_OUTSIDE"


class TestExemption:
    def test_the_testers_number_works_from_another_continent(self, client: TestClient):
        # The exempt rider asks from Herat's coordinates and is let through:
        # exemption beats geography, which is the whole point of the list.
        rider = auth(sign_in(client, "+93700000777"))
        allowed = _ask(client, rider, _first_journey(client, rider), **HERAT)
        assert allowed.status_code == 201, allowed.text
        done = client.post(
            f"/api/v1/ride-requests/{allowed.json()['data']['id']}/cancel",
            headers=rider,
        )
        assert done.status_code == 200, done.text
