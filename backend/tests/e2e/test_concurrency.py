"""The races, run for real.

Every guard these exercise was already true in a single-threaded read of the
code. That is exactly why they need this file: the bugs they close were all of
the form "two callers pass the same check before either commits", which no
sequential test can produce and no code read can rule out. Two threads, one
barrier, a real Postgres -- the loser must lose honestly.
"""

from __future__ import annotations

import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import auth, sign_in

# Dedicated personas. The other modules share the seeded rider and driver and
# are "written not to depend on each other's leftovers" -- but a race that
# swallows a trip's whole remainder and matches a ride IS a leftover, so these
# tests bring their own passenger and put every seat back before leaving.
RIDER_PHONE = "+93700000777"
DRIVER_PHONE = "+93700000020"


@pytest.fixture(scope="module")
def rider(client: TestClient) -> dict:
    return auth(sign_in(client, RIDER_PHONE))


@pytest.fixture(scope="module")
def driver(client: TestClient) -> dict:
    session = auth(sign_in(client, DRIVER_PHONE))
    client.post(
        "/api/v1/driver/status", json={"availability": "ONLINE"}, headers=session
    )
    return session


def _journeys(client: TestClient, headers: dict):
    """(origin_station, destination) pairs, walked the way the app walks them."""
    for district in client.get("/api/v1/geo/districts", headers=headers).json()["data"]:
        for village in client.get(
            f"/api/v1/geo/districts/{district['id']}/villages", headers=headers
        ).json()["data"]:
            for station in client.get(
                f"/api/v1/geo/villages/{village['id']}/stations", headers=headers
            ).json()["data"]:
                groups = client.get(
                    f"/api/v1/geo/stations/{station['id']}/destinations", headers=headers
                ).json()["data"]
                for group in groups:
                    for target in (group.get("children") or [group]):
                        yield station["id"], target["id"]


def _first_journey(client: TestClient, headers: dict) -> tuple[str, str]:
    for pair in _journeys(client, headers):
        return pair
    raise AssertionError("seed provided no journey")


def _race(call_a, call_b):
    """Fire two callables through one barrier; return both results."""
    barrier = threading.Barrier(2)
    results: dict[str, object] = {}

    def run(name, call):
        barrier.wait()
        results[name] = call()

    threads = [
        threading.Thread(target=run, args=("a", call_a)),
        threading.Thread(target=run, args=("b", call_b)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert set(results) == {"a", "b"}, "a racer never finished"
    return results["a"], results["b"]


def _search(client, headers, origin, destination, seat_count):
    return client.post(
        "/api/v1/trips/search",
        json={
            "origin_station_id": origin,
            "destination_id": destination,
            "seat_count": seat_count,
        },
        headers=headers,
    ).json()["data"]


class TestLastSeat:
    """Two bookings that each want everything the trip has left.

    Not pinned to a pristine trip: earlier modules may have taken seats, and
    the invariant does not care. Whatever is available, two transactions each
    demanding all of it can produce exactly one winner -- that IS the last-seat
    guarantee, stated without assuming the seed's arithmetic.
    """

    def test_exactly_one_booking_wins_the_remainder(self, client, rider):
        origin = destination = trip_id = None
        remaining = 0
        for o, d in _journeys(client, rider):
            for option in _search(client, rider, o, d, 1):
                if option["seats_available"] >= 2:
                    origin, destination = o, d
                    trip_id = option["trip_id"]
                    remaining = option["seats_available"]
                    break
            if trip_id:
                break
        assert trip_id, "no trip with two seats left anywhere in the seed"
        take = min(remaining, 4)  # per-booking maximum

        def book():
            return client.post(
                "/api/v1/bookings",
                json={
                    "trip_id": trip_id,
                    "seat_count": take,
                    "pickup_station_id": origin,
                    "dropoff_destination_id": destination,
                },
                # Distinct keys, or the idempotency layer would collapse the
                # race into one request and this test would prove nothing.
                headers={**rider, "Idempotency-Key": str(uuid.uuid4())},
            )

        first, second = _race(book, book)
        codes = sorted((first.status_code, second.status_code))
        assert codes == [200, 409], (first.text, second.text)

        winner = first if first.status_code == 200 else second
        loser = first if first.status_code == 409 else second
        assert loser.json()["error"]["code"] == "TRIP_SEATS_UNAVAILABLE"

        # The arithmetic after the dust settles.
        after = {
            o["trip_id"]: o["seats_available"]
            for o in _search(client, rider, origin, destination, 1)
        }
        assert after.get(trip_id, 0) == remaining - take

        # Put the seats back: the modules after this one share the seed.
        cancelled = client.post(
            f"/api/v1/bookings/{winner.json()['data']['id']}/cancel",
            json={"reason_code": "PASSENGER_CANCELLED"},
            headers=rider,
        )
        assert cancelled.status_code == 200, cancelled.text


class TestDoubleAccept:
    """One offer, accepted from two threads at once."""

    def test_the_second_accept_is_refused_not_doubled(self, client, rider, driver):
        origin, destination = _first_journey(client, rider)
        asked = client.post(
            "/api/v1/ride-requests",
            json={
                "origin_station_id": origin,
                "destination_id": destination,
                "passenger_count": 1,
                "offered_fare_minor": 90_000,
            },
            headers=rider,
        )
        assert asked.status_code == 201, asked.text
        request_id = asked.json()["data"]["id"]

        offered = client.post(
            f"/api/v1/driver/ride-requests/{request_id}/offer",
            json={"amount_minor": 95_000},
            headers=driver,
        )
        assert offered.status_code == 201, offered.text
        offer_id = offered.json()["data"]["id"]

        def accept():
            return client.post(
                f"/api/v1/fare-offers/{offer_id}/accept", headers=rider
            )

        first, second = _race(accept, accept)
        codes = sorted((first.status_code, second.status_code))
        assert codes == [200, 409], (first.text, second.text)

        loser = first if first.status_code == 409 else second
        assert loser.json()["error"]["code"] == "RIDE_REQUEST_NOT_OPEN"

        # One request, one trip, one driver -- not a ghost dispatch.
        mine = client.get("/api/v1/ride-requests", headers=rider).json()["data"]
        row = next(r for r in mine if r["id"] == request_id)
        assert row["status"] == "MATCHED"
        assert row["trip_id"]

        # The shared driver must walk out of this module as free as he walked
        # in: cancelling only the booking would leave him assigned to an empty
        # trip and unbookable for every module after this one. The driver-side
        # cancel is the sanctioned cascade -- trip, booking and seats together.
        undone = client.post(
            f"/api/v1/driver/trips/{row['trip_id']}/advance",
            json={"target": "CANCELLED", "reason_code": "VEHICLE_PROBLEM"},
            headers=driver,
        )
        assert undone.status_code == 200, undone.text


class TestSameKeyReplay:
    """Two requests, one idempotency key, fired through one barrier.

    The other races prove the loser is refused. This one proves the opposite
    contract: a retry of the SAME action must not lose -- it must receive the
    winner's answer, because on these connections the request that timed out
    at the handset very often succeeded at the server, and the passenger's
    next tap is the same booking, not a second one.
    """

    def test_both_callers_get_one_booking(self, client, rider):
        origin = destination = trip_id = None
        for o, d in _journeys(client, rider):
            for option in _search(client, rider, o, d, 1):
                if option["seats_available"] >= 1:
                    origin, destination, trip_id = o, d, option["trip_id"]
                    break
            if trip_id:
                break
        assert trip_id, "no seat anywhere in the seed"

        key = str(uuid.uuid4())

        def book():
            return client.post(
                "/api/v1/bookings",
                json={
                    "trip_id": trip_id,
                    "seat_count": 1,
                    "pickup_station_id": origin,
                    "dropoff_destination_id": destination,
                },
                headers={**rider, "Idempotency-Key": key},
            )

        first, second = _race(book, book)
        assert first.status_code == second.status_code == 200, (
            first.text, second.text,
        )
        a, b = first.json()["data"], second.json()["data"]
        assert a["id"] == b["id"], "one key produced two bookings"
        assert a["number"] == b["number"]

        client.post(
            f"/api/v1/bookings/{a['id']}/cancel",
            json={"reason_code": "PASSENGER_CANCELLED"},
            headers=rider,
        )
