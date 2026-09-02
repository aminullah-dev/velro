"""A dispatcher's offer is waiting in the driver's inbox.

The negotiated path has written a message for every driver an ask concerns
since ADR 0005; the dispatch path wrote the offer row and told nobody. Same
shape as test_notifications: no push transport is configured, so the row
must be there and honest about not having been delivered.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import auth, sign_in

DRIVER = "+93700000021"      # the seed's second driver, نجیب, with the SUV


@pytest.fixture(scope="module")
def driver(client: TestClient) -> dict:
    session = auth(sign_in(client, DRIVER))
    online = client.post(
        "/api/v1/driver/status", json={"availability": "ONLINE"}, headers=session
    )
    assert online.status_code == 200, online.text
    return session


def test_the_driver_offered_a_trip_finds_it_in_his_inbox(
    client: TestClient, admin_session: dict, driver: dict
) -> None:
    board = client.get("/api/v1/dispatch/unassigned", headers=admin_session).json()["data"]
    # A trip nobody has been asked about yet, so this press is the one that
    # offers it rather than the dispatcher's second tap answered with zero.
    # Sibling modules share this database and may already have offered every
    # seeded trip; that is their run, not a failure of this one.
    trip = next(
        (r for r in board if r["candidates"] >= 1 and r["open_offers"] == 0), None
    )
    if trip is None:
        pytest.skip("every candidate trip already carries an open offer")

    offered = client.post(f"/api/v1/dispatch/trips/{trip['id']}/offer", headers=admin_session)
    assert offered.status_code == 200, offered.text
    assert offered.json()["data"]["offers_made"] >= 1

    inbox = client.get("/api/v1/notifications", headers=driver).json()["data"]
    note = next(
        n
        for n in inbox["notifications"]
        if n["message_key"] == "notify.trip.offered" and n["payload"]["trip_id"] == trip["id"]
    )
    assert note["payload"]["trip_number"] == trip["number"]
    assert note["trip_id"] == trip["id"], "the driver needs to reach the trip from the message"
    # Nothing was delivered, and the row says so rather than claiming success.
    assert note["delivery_status"] == "FAILED"
    assert inbox["unread"] >= 1
