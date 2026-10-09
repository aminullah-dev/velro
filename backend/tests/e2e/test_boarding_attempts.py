"""The boarding code, and how many times a driver may guess it.

The code is short -- it is read aloud at a roadside -- and the trip's own
driver could try codes against it without limit: every wrong one answered
409 and cost nothing. Whoever can guess a code can mark a passenger aboard
who never got in the car.

Now a trip allows booking.verification_max_attempts wrong codes, then refuses
every code for booking.verification_lockout_seconds. The count is written in
a transaction of its own, because each wrong code is a refusal and the
request's own transaction is rolled back with it -- the trap the OTP counter
fell into first (test_otp_brute_force.py).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from tests.e2e.conftest import auth, road_ready_driver, sign_in

PASSENGER = "+93700000587"
DRIVER = "+93700000588"
KNOWN_CODE = "K7M2Q9"
#: The same code as a driver on a Persian keyboard types it.
KNOWN_CODE_EASTERN = "K۷M۲Q۹"


def _journey(client: TestClient, headers: dict) -> tuple[str, str]:
    for district in client.get("/api/v1/geo/districts", headers=headers).json()["data"]:
        for village in client.get(
            f"/api/v1/geo/districts/{district['id']}/villages", headers=headers
        ).json()["data"]:
            for station in client.get(
                f"/api/v1/geo/villages/{village['id']}/stations", headers=headers
            ).json()["data"]:
                destinations = client.get(
                    f"/api/v1/geo/stations/{station['id']}/destinations", headers=headers
                ).json()["data"]
                if destinations:
                    return station["id"], destinations[0]["id"]
    raise AssertionError("the seed produced no station with a destination")


@pytest.fixture(scope="module")
def boarding(client: TestClient, admin_session: dict) -> dict:
    """A negotiated ride with its driver standing at the pickup."""
    passenger = auth(sign_in(client, PASSENGER))
    driver, _ = road_ready_driver(client, admin_session, DRIVER, "BRD-5880")
    client.post("/api/v1/driver/status", headers=driver, json={"availability": "ONLINE"})

    origin, destination = _journey(client, passenger)
    asked = client.post(
        "/api/v1/ride-requests", headers=passenger,
        json={
            "origin_station_id": origin, "destination_id": destination,
            "passenger_count": 1, "offered_fare_minor": 30_000,
        },
    )
    assert asked.status_code == 201, asked.text
    offer = client.post(
        f"/api/v1/driver/ride-requests/{asked.json()['data']['id']}/offer",
        headers=driver, json={"amount_minor": 35_000},
    )
    assert offer.status_code in (200, 201), offer.text
    agreed = client.post(
        f"/api/v1/fare-offers/{offer.json()['data']['id']}/accept", headers=passenger
    )
    assert agreed.status_code == 200, agreed.text
    data = agreed.json()["data"]

    for target in ("DRIVER_ARRIVING", "ARRIVED_AT_PICKUP"):
        step = client.post(
            f"/api/v1/driver/trips/{data['trip_id']}/advance",
            headers=driver, json={"target": target},
        )
        assert step.status_code == 200, step.text

    # A code with digits in it, so the last test can type them the way a
    # Persian keyboard does. The generated one is kept for the length check.
    from infrastructure.db.models.trips import BookingRow
    from ui.api import deps

    with deps._session_factory()() as session:
        session.execute(
            update(BookingRow)
            .where(BookingRow.id == data["booking_id"])
            .values(verification_code=KNOWN_CODE)
        )
        session.commit()
    return {
        "driver": driver, "trip_id": data["trip_id"],
        "generated": data["verification_code"], "code": KNOWN_CODE,
    }


def _present(client: TestClient, boarding: dict, code: str):
    return client.post(
        f"/api/v1/driver/trips/{boarding['trip_id']}/verify-passenger",
        headers=boarding["driver"], json={"code": code},
    )


def _trip(trip_id: str):
    from infrastructure.db.models.trips import TripRow
    from ui.api import deps

    with deps._session_factory()() as session:
        return session.scalars(select(TripRow).where(TripRow.id == trip_id)).one()


def _wrong(real: str) -> str:
    return "ZZZZZZ" if real != "ZZZZZZ" else "YYYYYY"


def test_a_new_code_is_six_characters(boarding: dict) -> None:
    # Every driver build in the field takes 3 to 8 characters in this field,
    # and both passenger builds print whatever string they are given.
    assert len(boarding["generated"]) == 6


def test_the_driver_gets_a_limited_number_of_guesses(
    client: TestClient, boarding: dict
) -> None:
    from infrastructure.services.settings import DEFAULTS

    limit = DEFAULTS["booking.verification_max_attempts"]
    lockout = DEFAULTS["booking.verification_lockout_seconds"]
    wrong = _wrong(boarding["code"])

    remaining = []
    for _ in range(limit):
        refused = _present(client, boarding, wrong)
        assert refused.status_code == 409, refused.text
        body = refused.json()["error"]
        assert body["code"] == "BOOKING_VERIFICATION_FAILED"
        remaining.append(body["context"].get("attempts_remaining"))
    assert remaining == list(range(limit - 1, -1, -1))

    # The limit is spent: even the right code waits out the lockout, so a
    # driver who finally guesses right learns nothing from it.
    locked = _present(client, boarding, boarding["code"])
    assert locked.status_code == 429, (
        f"guess number {limit + 1} was still evaluated: {locked.text}"
    )
    body = locked.json()["error"]
    assert body["code"] == "BOOKING_VERIFICATION_LOCKED"
    assert 0 < body["context"]["retry_after_seconds"] <= lockout
    assert body["context"]["retry_after_minutes"] >= 1

    # Persisted, not remembered by the request that refused.
    trip = _trip(boarding["trip_id"])
    assert trip.boarding_locked_until is not None
    assert trip.boarding_failures == limit


def test_after_the_lockout_the_right_code_boards(
    client: TestClient, boarding: dict
) -> None:
    from datetime import UTC, datetime, timedelta

    from infrastructure.db.models.trips import TripRow
    from ui.api import deps

    # Wind the clock: the lockout ended a second ago.
    with deps._session_factory()() as session:
        session.execute(
            update(TripRow)
            .where(TripRow.id == boarding["trip_id"])
            .values(boarding_locked_until=datetime.now(UTC) - timedelta(seconds=1))
        )
        session.commit()

    # Typed with Eastern digits, by a build that does not fold them: the
    # server folds both sides of the comparison, so it boards -- rather than
    # matching the booking, refusing it, and charging an attempt for it.
    boarded = _present(client, boarding, KNOWN_CODE_EASTERN)
    assert boarded.status_code == 200, boarded.text
    assert boarded.json()["data"]["status"] == "ONBOARD"

    # A served lockout starts a fresh count, and a code that boarded someone
    # is not a failure.
    trip = _trip(boarding["trip_id"])
    assert trip.boarding_failures == 0
    assert trip.boarding_locked_until is None
