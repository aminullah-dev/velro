"""Telling people something happened.

A push is a convenience; the inbox is the record. In Ghorband the channel often
fails, so what these tests care about is that the message is written and
readable regardless, and that failing to send never costs anybody a ride.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import auth, road_ready_driver, sign_in


@pytest.fixture(scope="module")
def rider(client: TestClient) -> dict:
    return auth(sign_in(client, "+93700000120"))


def _working_driver(client: TestClient, phone: str) -> dict:
    """A driver who could actually turn up: approved, with an active vehicle.

    These fixtures used to sign in a fresh number and POST /driver/register,
    which leaves a driver PENDING with no vehicle. Every test passed, because
    the negotiated path had no gate at all -- somebody who had merely asked to
    become a driver could bid on a real journey and win it. Both paths check
    now, so the fixtures have to be drivers.
    """
    session = auth(sign_in(client, phone))
    client.post(
        "/api/v1/driver/status", json={"availability": "ONLINE"}, headers=session
    )
    return session


@pytest.fixture(scope="module")
def hauler(client: TestClient, admin_session: dict) -> dict:
    session, _ = road_ready_driver(
        client, admin_session, "+93700000121", "NTF-1121"
    )
    client.post(
        "/api/v1/driver/status", json={"availability": "ONLINE"}, headers=session
    )
    return session


@pytest.fixture(scope="module")
def rival(client: TestClient, admin_session: dict) -> dict:
    session, _ = road_ready_driver(
        client, admin_session, "+93700000122", "NTF-1122"
    )
    client.post(
        "/api/v1/driver/status", json={"availability": "ONLINE"}, headers=session
    )
    return session


def _release(client, *drivers) -> None:
    """Put every driver back to idle and online."""
    for driver in drivers:
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
def _idle_drivers(client: TestClient, hauler: dict, rival: dict):
    """Both drivers idle before and after every test in this module.

    A driver may hold only one live trip since the negotiated path started
    checking it, so a test that accepts an offer leaves its driver carrying a
    passenger. Cleaning up afterwards as well as before matters because these
    are the seeded drivers: leaving one mid-trip at the end of this module
    breaks the vertical-slice test that signs in as the same man.
    """
    _release(client, hauler, rival)
    yield
    _release(client, hauler, rival)


@pytest.fixture(scope="module")
def journey(client: TestClient, rider: dict) -> dict:
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
                dests = client.get(
                    f"/api/v1/geo/stations/{station['id']}/destinations", headers=rider
                ).json()["data"]
                if dests:
                    return {"station_id": station["id"], "destination_id": dests[0]["id"]}
    pytest.skip("no station with a destination")


def _ask(client: TestClient, who: dict, journey: dict, minor: int = 50_000) -> dict:
    r = client.post(
        "/api/v1/ride-requests",
        json={
            "origin_station_id": journey["station_id"],
            "destination_id": journey["destination_id"],
            "passenger_count": 1,
            "offered_fare_minor": minor,
        },
        headers=who,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _clear(client: TestClient, who: dict) -> None:
    for row in client.get("/api/v1/ride-requests", headers=who).json()["data"]:
        if row["status"] == "OPEN":
            client.post(f"/api/v1/ride-requests/{row['id']}/cancel", headers=who)


# -- devices -------------------------------------------------------------

def test_a_device_registers_and_moves_with_whoever_signs_in(
    client: TestClient, rider: dict, hauler: dict
) -> None:
    """Handsets are shared and reinstalled.

    Registering the same token under a second person must move it, not add a
    second owner -- otherwise a driver's ride offer goes to whoever had the
    phone last.
    """
    token = "token-shared-handset-0001"
    first = client.post(
        "/api/v1/devices",
        json={"token": token, "platform": "ANDROID", "app": "PASSENGER"},
        headers=rider,
    )
    assert first.status_code == 201, first.text

    second = client.post(
        "/api/v1/devices",
        json={"token": token, "platform": "ANDROID", "app": "DRIVER"},
        headers=hauler,
    )
    assert second.status_code == 201, second.text
    assert second.json()["data"]["id"] == first.json()["data"]["id"], "moved, not duplicated"
    assert second.json()["data"]["app"] == "DRIVER"


def test_signing_out_stops_the_handset_receiving(
    client: TestClient, rider: dict
) -> None:
    token = "token-to-forget-0002"
    client.post(
        "/api/v1/devices",
        json={"token": token, "platform": "ANDROID", "app": "PASSENGER"},
        headers=rider,
    )
    gone = client.delete(f"/api/v1/devices/{token}", headers=rider)
    assert gone.status_code == 200
    assert gone.json()["data"]["removed"] == 1


def test_one_person_cannot_unregister_anothers_device(
    client: TestClient, rider: dict, hauler: dict
) -> None:
    token = "token-not-yours-0003"
    client.post(
        "/api/v1/devices",
        json={"token": token, "platform": "ANDROID", "app": "PASSENGER"},
        headers=rider,
    )
    attempt = client.delete(f"/api/v1/devices/{token}", headers=hauler)
    # Nothing removed rather than an error: the token is simply not theirs.
    assert attempt.json()["data"]["removed"] == 0
    assert client.delete(f"/api/v1/devices/{token}", headers=rider).json()["data"]["removed"] == 1


# -- the inbox -----------------------------------------------------------

def test_an_offer_reaches_the_passengers_inbox(
    client: TestClient, rider: dict, hauler: dict, journey: dict
) -> None:
    """With no push transport configured, the message must still be waiting."""
    _clear(client, rider)
    asked = _ask(client, rider, journey, 50_000)
    client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 60_000}, headers=hauler,
    )

    inbox = client.get("/api/v1/notifications", headers=rider).json()["data"]
    note = next(n for n in inbox["notifications"] if n["message_key"] == "notify.offer.received")
    assert note["payload"]["amount_minor"] == 60_000
    assert note["payload"]["ride_request_id"] == asked["id"]
    # Honest about what happened: nothing was delivered, and the row says so
    # rather than claiming success.
    assert note["delivery_status"] == "FAILED"
    assert inbox["unread"] >= 1
    _clear(client, rider)


def test_the_chosen_driver_is_told_and_the_others_are_too(
    client: TestClient, rider: dict, hauler: dict, journey: dict
) -> None:
    _clear(client, rider)
    asked = _ask(client, rider, journey, 50_000)
    offer = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 55_000}, headers=hauler,
    ).json()["data"]

    taken = client.post(f"/api/v1/fare-offers/{offer['id']}/accept", headers=rider)
    assert taken.status_code == 200, taken.text

    inbox = client.get("/api/v1/notifications", headers=hauler).json()["data"]
    told = next(
        n for n in inbox["notifications"] if n["message_key"] == "notify.offer.accepted"
    )
    assert told["payload"]["amount_minor"] == 55_000
    assert told["booking_id"], "the driver needs to reach the trip from the message"


def test_the_drivers_who_lost_are_told_too(
    client: TestClient, rider: dict, hauler: dict, rival: dict, journey: dict
) -> None:
    """Otherwise they drive to a station where the passenger has already gone.

    The one notification nobody asks for and everybody needs: losing quietly
    costs a driver a journey across a valley.
    """
    _clear(client, rider)
    asked = _ask(client, rider, journey, 50_000)
    chosen = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 54_000}, headers=hauler,
    ).json()["data"]
    client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 62_000}, headers=rival,
    )

    assert client.post(
        f"/api/v1/fare-offers/{chosen['id']}/accept", headers=rider
    ).status_code == 200

    inbox = client.get("/api/v1/notifications", headers=rival).json()["data"]
    told = [n for n in inbox["notifications"] if n["message_key"] == "notify.offer.declined"]
    assert told, "the driver who lost was left waiting"
    assert told[0]["payload"]["ride_request_id"] == asked["id"]

    # And the one who won is not told they lost.
    winner = client.get("/api/v1/notifications", headers=hauler).json()["data"]
    assert not [
        n for n in winner["notifications"]
        if n["message_key"] == "notify.offer.declined"
        and n["payload"].get("ride_request_id") == asked["id"]
    ]


def test_reading_the_inbox_clears_the_count(
    client: TestClient, rider: dict, hauler: dict, journey: dict
) -> None:
    _clear(client, rider)
    asked = _ask(client, rider, journey)
    client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 52_000}, headers=hauler,
    )
    assert client.get("/api/v1/notifications", headers=rider).json()["data"]["unread"] > 0

    marked = client.post("/api/v1/notifications/read", json={}, headers=rider)
    assert marked.status_code == 200
    assert marked.json()["data"]["unread"] == 0
    _clear(client, rider)


def test_one_person_cannot_read_anothers_inbox(
    client: TestClient, rider: dict, hauler: dict
) -> None:
    mine = client.get("/api/v1/notifications", headers=rider).json()["data"]
    theirs = client.get("/api/v1/notifications", headers=hauler).json()["data"]
    my_ids = {n["id"] for n in mine["notifications"]}
    their_ids = {n["id"] for n in theirs["notifications"]}
    assert not (my_ids & their_ids)


def test_marking_read_cannot_touch_someone_elses_notification(
    client: TestClient, rider: dict, hauler: dict, journey: dict
) -> None:
    _clear(client, rider)
    asked = _ask(client, rider, journey)
    client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 51_000}, headers=hauler,
    )
    mine = client.get("/api/v1/notifications", headers=rider).json()["data"]
    unread_id = next(n["id"] for n in mine["notifications"] if n["read_at"] is None)

    # A driver naming a passenger's notification id marks nothing.
    r = client.post(
        "/api/v1/notifications/read", json={"ids": [unread_id]}, headers=hauler
    )
    assert r.json()["data"]["marked"] == 0
    still = client.get("/api/v1/notifications", headers=rider).json()["data"]
    assert any(n["id"] == unread_id and n["read_at"] is None for n in still["notifications"])
    _clear(client, rider)


# -- the property that matters most --------------------------------------

def test_a_broken_notifier_never_costs_anybody_a_ride(
    client: TestClient, rider: dict, hauler: dict, journey: dict
) -> None:
    """Delivery is best effort, always.

    If telling someone can fail the thing it is telling them about, then a bad
    afternoon on the network becomes an afternoon with no rides.
    """
    from ui.api import deps

    class Broken:
        def notify(self, **_):
            raise RuntimeError("the notifier is down")

    _clear(client, rider)
    client.app.dependency_overrides[deps.notifier] = lambda: Broken()
    try:
        asked = _ask(client, rider, journey, 50_000)
        offered = client.post(
            f"/api/v1/driver/ride-requests/{asked['id']}/offer",
            json={"amount_minor": 58_000}, headers=hauler,
        )
        assert offered.status_code == 201, offered.text

        taken = client.post(
            f"/api/v1/fare-offers/{offered.json()['data']['id']}/accept", headers=rider
        )
        assert taken.status_code == 200, taken.text
        assert taken.json()["data"]["agreed_fare"]["amount_minor"] == 58_000
    finally:
        client.app.dependency_overrides.pop(deps.notifier, None)
