"""A matched request tells the passenger which booking it became.

Before this, a ride request that closed with a driver actually accepted
(MATCHED, with a trip and a booking already made) looked identical on refetch
to one that was genuinely cancelled or expired -- the read model carried a
trip id but nothing a passenger's app could use to route back to the booking
itself. This proves the read model now carries that link.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import auth, road_ready_driver, sign_in

pytestmark = pytest.mark.integration

RIDER = "+93700000790"
DRIVER = "+93700000791"


@pytest.fixture(scope="module")
def rider(client: TestClient) -> dict:
    return auth(sign_in(client, RIDER))


@pytest.fixture(scope="module")
def driver(client: TestClient, admin_session: dict) -> dict:
    """An approved driver, with a vehicle, online -- one who can take work."""
    session, _ = road_ready_driver(client, admin_session, DRIVER, "REP-9101")
    client.post(
        "/api/v1/driver/status", json={"availability": "ONLINE"}, headers=session
    )
    return session


@pytest.fixture(scope="module")
def journey(client: TestClient, rider: dict) -> dict:
    """A real station and a real destination to travel between."""
    districts = client.get("/api/v1/geo/districts", headers=rider).json()["data"]
    for district in districts:
        villages = client.get(
            f"/api/v1/geo/districts/{district['id']}/villages", headers=rider
        ).json()["data"]
        for village in villages:
            stations = client.get(
                f"/api/v1/geo/villages/{village['id']}/stations", headers=rider
            ).json()["data"]
            for station in stations:
                destinations = client.get(
                    f"/api/v1/geo/stations/{station['id']}/destinations",
                    headers=rider,
                ).json()["data"]
                if destinations:
                    return {
                        "station_id": station["id"],
                        "destination_id": destinations[0]["id"],
                    }
    pytest.skip("the seed produced no station with a destination")


def _release(client: TestClient, driver: dict) -> None:
    """Put the driver back to idle and online for the next test."""
    trip = client.get("/api/v1/driver/trips/current", headers=driver)
    data = trip.json().get("data") if trip.status_code == 200 else None
    if data and data.get("trip"):
        client.post(
            f"/api/v1/driver/trips/{data['trip']['id']}/advance",
            headers=driver, json={"target": "CANCELLED"},
        )
    client.post(
        "/api/v1/driver/status", json={"availability": "ONLINE"}, headers=driver
    )


@pytest.fixture(autouse=True)
def _idle_driver(client: TestClient, driver: dict):
    _release(client, driver)
    yield
    _release(client, driver)


def test_a_matched_request_carries_its_booking_id(
    client: TestClient, rider: dict, driver: dict, journey: dict
) -> None:
    asked = client.post(
        "/api/v1/ride-requests",
        json={
            "origin_station_id": journey["station_id"],
            "destination_id": journey["destination_id"],
            "passenger_count": 1,
            "offered_fare_minor": 50_000,
        },
        headers=rider,
    ).json()["data"]
    offer = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 50_000}, headers=driver,
    ).json()["data"]

    accepted = client.post(
        f"/api/v1/fare-offers/{offer['id']}/accept", headers=rider
    )
    assert accepted.status_code == 200, accepted.text
    booking_id = accepted.json()["data"]["booking_id"]

    mine = client.get("/api/v1/ride-requests", headers=rider).json()["data"]
    matched = next(r for r in mine if r["id"] == asked["id"])
    assert matched["status"] == "MATCHED"
    assert matched["trip_id"] == accepted.json()["data"]["trip_id"]
    assert matched["booking_id"] == booking_id


def test_an_open_request_carries_no_booking_id(
    client: TestClient, rider: dict, journey: dict
) -> None:
    asked = client.post(
        "/api/v1/ride-requests",
        json={
            "origin_station_id": journey["station_id"],
            "destination_id": journey["destination_id"],
            "passenger_count": 1,
            "offered_fare_minor": 50_000,
        },
        headers=rider,
    ).json()["data"]
    try:
        mine = client.get("/api/v1/ride-requests", headers=rider).json()["data"]
        mine_row = next(r for r in mine if r["id"] == asked["id"])
        assert mine_row["status"] == "OPEN"
        assert mine_row["booking_id"] is None
    finally:
        client.post(f"/api/v1/ride-requests/{asked['id']}/cancel", headers=rider)
