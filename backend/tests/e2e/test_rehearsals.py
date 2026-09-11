"""Rehearsals never meet real journeys.

A number on OTP_TEST_NUMBERS is nobody's handset, so a ride it asks for is a
rehearsal -- App Review's, from a desk in Cupertino, is the one this exists
for. A real driver must never see it (he would drive to a station for
nobody), and a rehearsing driver must never see a real passenger (she would
wait for a car that is not coming).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import REHEARSAL_PHONES, auth, road_ready_driver, sign_in

pytestmark = pytest.mark.integration

REVIEWER, REHEARSING_DRIVER = REHEARSAL_PHONES
REAL_RIDER = "+93700000705"
REAL_DRIVER = "+93700000706"


def _journey(client: TestClient, headers: dict) -> dict:
    for district in client.get("/api/v1/geo/districts", headers=headers).json()["data"]:
        villages = client.get(
            f"/api/v1/geo/districts/{district['id']}/villages", headers=headers
        ).json()["data"]
        for village in villages:
            stations = client.get(
                f"/api/v1/geo/villages/{village['id']}/stations", headers=headers
            ).json()["data"]
            for station in stations:
                destinations = client.get(
                    f"/api/v1/geo/stations/{station['id']}/destinations", headers=headers
                ).json()["data"]
                if destinations:
                    return {
                        "origin_station_id": station["id"],
                        "destination_id": destinations[0]["id"],
                    }
    pytest.skip("the seed produced no station with a destination")


def _ask(client: TestClient, passenger: dict) -> str:
    for row in client.get("/api/v1/ride-requests", headers=passenger).json()["data"]:
        if row["status"] == "OPEN":
            client.post(f"/api/v1/ride-requests/{row['id']}/cancel", headers=passenger)
    asked = client.post(
        "/api/v1/ride-requests", headers=passenger,
        json={**_journey(client, passenger), "passenger_count": 1, "offered_fare_minor": 20_000},
    )
    assert asked.status_code == 201, asked.text
    return asked.json()["data"]["id"]


def _board(client: TestClient, driver: dict) -> set[str]:
    listed = client.get("/api/v1/driver/ride-requests", headers=driver)
    assert listed.status_code == 200, listed.text
    return {row["id"] for row in listed.json()["data"]}


@pytest.fixture(scope="module")
def people(client: TestClient, admin_session: dict) -> dict:
    reviewer = sign_in(client, REVIEWER)
    real_rider = auth(sign_in(client, REAL_RIDER))
    rehearsing, _ = road_ready_driver(client, admin_session, REHEARSING_DRIVER, "REH-0143")
    real, _ = road_ready_driver(client, admin_session, REAL_DRIVER, "REH-0706")
    for driver in (rehearsing, real):
        client.post("/api/v1/driver/status", headers=driver, json={"availability": "ONLINE"})
    return {
        "reviewer": auth(reviewer),
        "real_rider": real_rider,
        "rehearsing_driver": rehearsing,
        "real_driver": real,
    }


def test_the_reviewer_needs_no_message_and_no_fence(client: TestClient, people: dict):
    # sign_in already proved the code came back in the answer; the ask below
    # carries no coordinates, and is accepted from wherever App Review sits.
    assert _ask(client, people["reviewer"])


def test_a_rehearsal_is_seen_by_rehearsing_drivers_only(client: TestClient, people: dict):
    rehearsal = _ask(client, people["reviewer"])
    real = _ask(client, people["real_rider"])

    assert rehearsal in _board(client, people["rehearsing_driver"])
    assert real not in _board(client, people["rehearsing_driver"])

    assert real in _board(client, people["real_driver"])
    assert rehearsal not in _board(client, people["real_driver"])


def test_a_hidden_request_cannot_be_offered_on_by_its_id(client: TestClient, people: dict):
    rehearsal = _ask(client, people["reviewer"])
    real = _ask(client, people["real_rider"])
    for driver, request_id in (
        (people["real_driver"], rehearsal),
        (people["rehearsing_driver"], real),
    ):
        refused = client.post(
            f"/api/v1/driver/ride-requests/{request_id}/offer",
            headers=driver, json={"amount_minor": 25_000},
        )
        assert refused.status_code == 404, refused.text
        assert refused.json()["error"]["code"] == "RIDE_REQUEST_NOT_FOUND"

    # And the rehearsal still works end to end between its own two people.
    offered = client.post(
        f"/api/v1/driver/ride-requests/{rehearsal}/offer",
        headers=people["rehearsing_driver"], json={"amount_minor": 25_000},
    )
    assert offered.status_code == 201, offered.text
    for passenger in (people["reviewer"], people["real_rider"]):
        for row in client.get("/api/v1/ride-requests", headers=passenger).json()["data"]:
            if row["status"] == "OPEN":
                client.post(f"/api/v1/ride-requests/{row['id']}/cancel", headers=passenger)
