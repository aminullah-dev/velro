"""The accept, retried -- and only ever by the person who made it.

Section 89's decisive tap had none of the protection a booking or the ask
carries: a passenger whose accept landed but whose answer never arrived could
only try again as a stranger, and be refused. Giving it a key was tried once
and reverted, because the key was the offer id, the driver holds the offer
id, and the stored answer -- the passenger's boarding code among it -- opened
for whoever could name the key.

These tests are the contract that replaced it (ADR 0013): the same passenger
with the same key gets the same journey back, once, however the retry
arrives; nobody else gets anything; and the code that lets the passenger into
the car is read by that passenger alone.

Every account here is a test number answered by the debug echo; no SMS is
sent by any of it.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import auth, road_ready_driver, sign_in

pytestmark = pytest.mark.integration

PASSENGER_A = "+93700000792"
PASSENGER_B = "+93700000793"
DRIVER_ONE = "+93700000794"
DRIVER_TWO = "+93700000795"

ACCEPT = "/api/v1/fare-offers/{}/accept"


@pytest.fixture(scope="module")
def rider_a(client: TestClient) -> dict:
    return auth(sign_in(client, PASSENGER_A))


@pytest.fixture(scope="module")
def rider_b(client: TestClient) -> dict:
    return auth(sign_in(client, PASSENGER_B))


@pytest.fixture(scope="module")
def driver_one(client: TestClient, admin_session: dict) -> dict:
    session, _ = road_ready_driver(client, admin_session, DRIVER_ONE, "REP-9104")
    return session


@pytest.fixture(scope="module")
def driver_two(client: TestClient, admin_session: dict) -> dict:
    session, _ = road_ready_driver(client, admin_session, DRIVER_TWO, "REP-9105")
    return session


@pytest.fixture(scope="module")
def journey(client: TestClient, rider_a: dict) -> dict:
    """A real station and a real destination to travel between."""
    districts = client.get("/api/v1/geo/districts", headers=rider_a).json()["data"]
    for district in districts:
        villages = client.get(
            f"/api/v1/geo/districts/{district['id']}/villages", headers=rider_a
        ).json()["data"]
        for village in villages:
            stations = client.get(
                f"/api/v1/geo/villages/{village['id']}/stations", headers=rider_a
            ).json()["data"]
            for station in stations:
                destinations = client.get(
                    f"/api/v1/geo/stations/{station['id']}/destinations",
                    headers=rider_a,
                ).json()["data"]
                if destinations:
                    return {
                        "station_id": station["id"],
                        "destination_id": destinations[0]["id"],
                    }
    pytest.skip("the seed produced no station with a destination")


def _release(client: TestClient, driver: dict) -> None:
    """Back to idle and online: each accept leaves a driver carrying someone."""
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


def _withdraw_open_ask(client: TestClient, rider: dict) -> None:
    mine = client.get("/api/v1/ride-requests", headers=rider).json()["data"]
    for row in mine:
        if row["status"] == "OPEN":
            client.post(f"/api/v1/ride-requests/{row['id']}/cancel", headers=rider)


@pytest.fixture(autouse=True)
def _clean_slate(
    client: TestClient, rider_a: dict, rider_b: dict, driver_one: dict, driver_two: dict
):
    for driver in (driver_one, driver_two):
        _release(client, driver)
    for rider in (rider_a, rider_b):
        _withdraw_open_ask(client, rider)
    yield
    for driver in (driver_one, driver_two):
        _release(client, driver)
    for rider in (rider_a, rider_b):
        _withdraw_open_ask(client, rider)


def _ask(client: TestClient, rider: dict, journey: dict, fare: int = 50_000) -> dict:
    asked = client.post(
        "/api/v1/ride-requests",
        json={
            "origin_station_id": journey["station_id"],
            "destination_id": journey["destination_id"],
            "passenger_count": 1,
            "offered_fare_minor": fare,
        },
        headers=rider,
    )
    assert asked.status_code == 201, asked.text
    return asked.json()["data"]


def _offer(client: TestClient, driver: dict, request_id: str, amount: int = 50_000) -> dict:
    made = client.post(
        f"/api/v1/driver/ride-requests/{request_id}/offer",
        json={"amount_minor": amount}, headers=driver,
    )
    assert made.status_code == 201, made.text
    return made.json()["data"]


def _accept(client: TestClient, who: dict, offer_id: str, key: str):
    return client.post(ACCEPT.format(offer_id), headers={**who, "Idempotency-Key": key})


def _race(call_a, call_b):
    barrier = threading.Barrier(2)
    results: dict[str, object] = {}

    def run(name, call):
        barrier.wait()
        results[name] = call()

    threads = [threading.Thread(target=run, args=("a", call_a)),
               threading.Thread(target=run, args=("b", call_b))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results["a"], results["b"]


# -- the same passenger, again ---------------------------------------------

def test_the_same_passenger_with_the_same_key_gets_the_same_ride(
    client, rider_a, driver_one, journey
) -> None:
    """The ordinary retry: the tap landed, the answer did not, the next tap
    carries the same key a moment later."""
    asked = _ask(client, rider_a, journey)
    offer = _offer(client, driver_one, asked["id"])
    key = str(uuid.uuid4())

    first = _accept(client, rider_a, offer["id"], key)
    assert first.status_code == 200, first.text
    second = _accept(client, rider_a, offer["id"], key)
    assert second.status_code == 200, second.text

    assert first.json()["data"] == second.json()["data"]
    assert first.json()["data"]["verification_code"]


def test_the_same_passenger_racing_themself_gets_one_ride(
    client, rider_a, driver_one, journey
) -> None:
    """The transport retry racing the person's own tap: both arrive at once.

    The request-row lock decides who builds the journey; the loser, having
    waited on that lock, finds the request already matched. Because it is the
    same account with the same key for the same request, it is handed the
    winner's answer rather than a refusal -- a lost response must never cost
    the passenger the ride they already have.
    """
    asked = _ask(client, rider_a, journey)
    offer = _offer(client, driver_one, asked["id"])
    key = str(uuid.uuid4())

    first, second = _race(
        lambda: _accept(client, rider_a, offer["id"], key),
        lambda: _accept(client, rider_a, offer["id"], key),
    )
    assert first.status_code == second.status_code == 200, (first.text, second.text)
    assert first.json()["data"] == second.json()["data"]

    mine = client.get("/api/v1/ride-requests", headers=rider_a).json()["data"]
    matched = next(r for r in mine if r["id"] == asked["id"])
    assert matched["status"] == "MATCHED"
    assert matched["trip_id"] == first.json()["data"]["trip_id"]
    assert matched["booking_id"] == first.json()["data"]["booking_id"]


def test_a_refused_accept_does_not_spend_the_key(
    client, rider_a, driver_one, journey
) -> None:
    """Only a success is remembered. A driver who has gone offline refuses the
    accept; when he is back the same key, the same tap, must go through."""
    asked = _ask(client, rider_a, journey)
    offer = _offer(client, driver_one, asked["id"])
    key = str(uuid.uuid4())

    client.post("/api/v1/driver/status", json={"availability": "OFFLINE"}, headers=driver_one)
    refused = _accept(client, rider_a, offer["id"], key)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "DRIVER_OFFLINE"

    client.post("/api/v1/driver/status", json={"availability": "ONLINE"}, headers=driver_one)
    accepted = _accept(client, rider_a, offer["id"], key)
    assert accepted.status_code == 200, accepted.text


# -- the same key, a different request ---------------------------------------

def test_the_same_key_carried_to_a_different_offer_is_refused(
    client, rider_a, driver_one, driver_two, journey
) -> None:
    """The key names one request. Presented with another offer it is a client
    bug, and the answer is a refusal -- not the first offer's ride replayed
    under the second's name, and not the second offer's stale status either."""
    asked = _ask(client, rider_a, journey)
    first_offer = _offer(client, driver_one, asked["id"], 50_000)
    second_offer = _offer(client, driver_two, asked["id"], 55_000)
    key = str(uuid.uuid4())

    taken = _accept(client, rider_a, first_offer["id"], key)
    assert taken.status_code == 200, taken.text

    carried = _accept(client, rider_a, second_offer["id"], key)
    assert carried.status_code == 409, carried.text
    assert carried.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert "verification_code" not in carried.text

    # And with an honest, fresh key the second offer answers with its own
    # state: the key scope hid nothing.
    fresh = _accept(client, rider_a, second_offer["id"], str(uuid.uuid4()))
    assert fresh.status_code == 409, fresh.text
    assert fresh.json()["error"]["code"] != "IDEMPOTENCY_KEY_REUSED"


def test_the_same_key_with_a_different_body_is_refused_on_the_ask(
    client, rider_a, journey
) -> None:
    """The ask has a body; the same key with a different one is the same bug."""
    key = str(uuid.uuid4())
    body = {
        "origin_station_id": journey["station_id"],
        "destination_id": journey["destination_id"],
        "passenger_count": 1,
        "offered_fare_minor": 50_000,
    }
    opened = client.post(
        "/api/v1/ride-requests", json=body, headers={**rider_a, "Idempotency-Key": key}
    )
    assert opened.status_code == 201, opened.text

    changed = client.post(
        "/api/v1/ride-requests",
        json={**body, "offered_fare_minor": 60_000},
        headers={**rider_a, "Idempotency-Key": key},
    )
    assert changed.status_code == 409, changed.text
    assert changed.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_the_same_key_on_another_endpoint_replays_nothing(
    client, rider_a, driver_one, journey
) -> None:
    """A key is scoped to its operation: the accept's key, sent to the ask,
    finds no stored answer and simply runs the ask."""
    asked = _ask(client, rider_a, journey)
    offer = _offer(client, driver_one, asked["id"])
    key = str(uuid.uuid4())
    accepted = _accept(client, rider_a, offer["id"], key)
    assert accepted.status_code == 200, accepted.text

    elsewhere = client.post(
        "/api/v1/ride-requests",
        json={
            "origin_station_id": journey["station_id"],
            "destination_id": journey["destination_id"],
            "passenger_count": 1,
            "offered_fare_minor": 50_000,
        },
        headers={**rider_a, "Idempotency-Key": key},
    )
    assert elsewhere.status_code == 201, elsewhere.text
    assert elsewhere.json()["data"]["status"] == "OPEN"
    assert "verification_code" not in elsewhere.text


# -- somebody else, with the passenger's key --------------------------------

def test_another_passenger_with_the_same_key_gets_nothing(
    client, rider_a, rider_b, driver_one, journey
) -> None:
    asked = _ask(client, rider_a, journey)
    offer = _offer(client, driver_one, asked["id"])
    key = str(uuid.uuid4())

    accepted = _accept(client, rider_a, offer["id"], key)
    assert accepted.status_code == 200, accepted.text
    code = accepted.json()["data"]["verification_code"]

    stranger = _accept(client, rider_b, offer["id"], key)
    assert stranger.status_code == 403, stranger.text
    assert stranger.json()["error"]["code"] == "PERMISSION_DENIED"
    assert "verification_code" not in stranger.text
    assert code not in stranger.text
    assert accepted.json()["data"]["booking_id"] not in stranger.text

    # Nor is the journey visible to B through the read side.
    theirs = client.get("/api/v1/ride-requests", headers=rider_b).json()["data"]
    assert all(r["id"] != asked["id"] for r in theirs)


def test_the_driver_who_made_the_offer_cannot_replay_the_accept(
    client, rider_a, driver_one, driver_two, journey
) -> None:
    """The exact hole the first attempt opened. The driver legitimately holds
    the offer id -- it is his own bid -- and knows the endpoint. With the
    passenger's key in hand he still gets a refusal and no code."""
    asked = _ask(client, rider_a, journey)
    offer = _offer(client, driver_one, asked["id"])
    key = str(uuid.uuid4())

    accepted = _accept(client, rider_a, offer["id"], key)
    assert accepted.status_code == 200, accepted.text
    code = accepted.json()["data"]["verification_code"]

    for driver in (driver_one, driver_two):
        replayed = _accept(client, driver, offer["id"], key)
        assert replayed.status_code == 403, replayed.text
        assert replayed.json()["error"]["code"] == "PERMISSION_DENIED"
        assert "verification_code" not in replayed.text
        assert code not in replayed.text

    # Even the key built the way the reverted client built it -- from the
    # offer id alone, which the driver can construct without being told.
    guessed = _accept(client, driver_one, offer["id"], f"accept_offer:{offer['id']}")
    assert guessed.status_code == 403, guessed.text
    assert code not in guessed.text


def test_the_boarding_code_reaches_only_the_passenger(
    client, rider_a, driver_one, journey
) -> None:
    """The code exists so the driver can be told it at the door, by the
    passenger. It is on the passenger's booking, and nowhere the driver reads."""
    asked = _ask(client, rider_a, journey)
    offer = _offer(client, driver_one, asked["id"])
    key = str(uuid.uuid4())

    accepted = _accept(client, rider_a, offer["id"], key)
    assert accepted.status_code == 200, accepted.text
    data = accepted.json()["data"]
    code = data["verification_code"]
    assert code

    own = client.get(f"/api/v1/bookings/{data['booking_id']}", headers=rider_a)
    assert own.status_code == 200, own.text
    assert own.json()["data"]["verification_code"] == code

    current = client.get("/api/v1/driver/trips/current", headers=driver_one)
    assert current.status_code == 200, current.text
    assert current.json()["data"]["trip"]["id"] == data["trip_id"]
    assert code not in current.text
    assert "verification_code" not in current.text
