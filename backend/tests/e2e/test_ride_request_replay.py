"""The ask, retried.

The negotiated path is the journey the product actually implements, and its
first move -- the passenger's ask -- rings every online driver. A booking has
carried an idempotency key from the start; the ask did not. On the connections
this product targets the request that times out at the handset very often
succeeded at the server, and without a key the passenger's next tap was a
second request, refused as "already open" -- or, two threads apart, two open
requests and every driver rung twice.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import auth, sign_in

pytestmark = pytest.mark.integration

RIDER = "+93700000779"


@pytest.fixture(scope="module")
def rider(client: TestClient) -> dict:
    return auth(sign_in(client, RIDER))


def _journey(client: TestClient, headers: dict) -> tuple[str, str]:
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
    return station["id"], charikar["id"]


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


def test_the_same_ask_twice_is_one_request(client: TestClient, rider: dict) -> None:
    origin, destination = _journey(client, rider)
    key = str(uuid.uuid4())

    def ask():
        return client.post(
            "/api/v1/ride-requests",
            json={"origin_station_id": origin, "destination_id": destination,
                  "passenger_count": 1, "offered_fare_minor": 80_000},
            headers={**rider, "Idempotency-Key": key},
        )

    first, second = _race(ask, ask)
    assert first.status_code == second.status_code == 201, (first.text, second.text)
    a, b = first.json()["data"], second.json()["data"]
    assert a["id"] == b["id"], "one key produced two requests"

    mine = client.get("/api/v1/ride-requests", headers=rider).json()["data"]
    assert sum(1 for r in mine if r["status"] == "OPEN") == 1

    cancelled = client.post(f"/api/v1/ride-requests/{a['id']}/cancel", headers=rider)
    assert cancelled.status_code == 200, cancelled.text


def test_a_different_ask_is_still_refused_while_one_is_open(
    client: TestClient, rider: dict
) -> None:
    """The rule the key must not weaken: one open request per passenger."""
    origin, destination = _journey(client, rider)
    body = {"origin_station_id": origin, "destination_id": destination,
            "passenger_count": 1, "offered_fare_minor": 80_000}
    opened = client.post(
        "/api/v1/ride-requests", json=body,
        headers={**rider, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert opened.status_code == 201, opened.text
    try:
        again = client.post(
            "/api/v1/ride-requests", json=body,
            headers={**rider, "Idempotency-Key": str(uuid.uuid4())},
        )
        assert again.status_code == 409, again.text
        assert again.json()["error"]["code"] == "RIDE_REQUEST_ALREADY_OPEN"
    finally:
        client.post(
            f"/api/v1/ride-requests/{opened.json()['data']['id']}/cancel", headers=rider
        )
