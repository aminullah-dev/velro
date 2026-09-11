"""Deleting your own account, through the same door a handset uses.

What the privacy page promises, checked from outside: the name, the number,
the documents and every session go; the trips and the money stay, without the
name; and the same SIM can start again as somebody new. Plus the three times
the answer is "not yet", each of which the person can do something about.

Numbers +93700000700-709 belong to this module and nothing else.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.e2e.conftest import auth, road_ready_driver, sign_in

pytestmark = pytest.mark.integration

LEAVER = "+93700000700"
BOOKED = "+93700000701"
BOOKED_DRIVER = "+93700000702"
LEAVING_DRIVER = "+93700000703"
ASKER = "+93700000704"


def _journey(client: TestClient, headers: dict) -> dict:
    """A real station with a real destination, walked out of the seed."""
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


def _ask(client: TestClient, passenger: dict, note: str | None = None) -> str:
    body = {**_journey(client, passenger), "passenger_count": 1, "offered_fare_minor": 20_000}
    if note is not None:
        body["note"] = note
    asked = client.post("/api/v1/ride-requests", headers=passenger, json=body)
    assert asked.status_code == 201, asked.text
    return asked.json()["data"]["id"]


def _online(client: TestClient, driver: dict) -> None:
    online = client.post(
        "/api/v1/driver/status", headers=driver, json={"availability": "ONLINE"}
    )
    assert online.status_code == 200, online.text


def _db():
    from ui.api import deps

    return deps._session_factory()()


# -- a passenger leaves ------------------------------------------------------


@pytest.fixture(scope="module")
def before(client: TestClient) -> dict:
    """Her account as it was, with something in every place that holds her:
    a name, a request still in the air with a note on it, two sessions."""
    first = sign_in(client, LEAVER)
    second = sign_in(client, LEAVER)
    headers = auth(first)
    named = client.patch("/api/v1/auth/me", headers=headers, json={"full_name": "Gul Bibi"})
    assert named.status_code == 200, named.text
    request_id = _ask(client, headers, note="near the mosque, blue gate")
    deleted = client.delete("/api/v1/auth/me", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["data"] == {"deleted": True}
    return {"first": first, "second": second, "request_id": request_id}


class TestAPassengerLeaves:
    def test_every_session_is_over_at_once(self, client: TestClient, before: dict):
        # The phone that asked, and the other phone that did not.
        for session in (before["first"], before["second"]):
            refused = client.get("/api/v1/auth/me", headers=auth(session))
            assert refused.status_code == 401, refused.text
            renewed = client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": session["refresh_token"], "device_id": "test-device"},
            )
            assert renewed.status_code == 401, renewed.text

    def test_nothing_that_names_her_is_left(self, client: TestClient, before: dict):
        from infrastructure.db.models.identity import OtpChallengeRow, UserRoleRow, UserRow
        from infrastructure.db.models.ops import AuditLogRow
        from infrastructure.db.models.trips import RideRequestRow

        with _db() as session:
            user = session.get(UserRow, before["first"]["user_id"])
            assert user.phone is None
            assert user.full_name is None
            assert user.status == "DEACTIVATED"
            request = session.get(RideRequestRow, before["request_id"])
            # Withdrawn, as if she had tapped cancel, and her words are gone.
            assert request.status == "CANCELLED"
            assert request.note is None
            assert not session.scalars(
                select(UserRoleRow).where(
                    UserRoleRow.user_id == user.id, UserRoleRow.deleted_at.is_(None)
                )
            ).all()
            assert not session.scalars(
                select(OtpChallengeRow).where(OtpChallengeRow.phone == LEAVER)
            ).all()
            # The audit trail says a name was recorded, and no longer says which.
            for entry in session.scalars(
                select(AuditLogRow).where(AuditLogRow.entity_id == user.id)
            ).all():
                assert "Gul Bibi" not in str(entry.before) + str(entry.after)
            deleted = session.scalars(
                select(AuditLogRow).where(
                    AuditLogRow.entity_id == user.id,
                    AuditLogRow.action == "user.deleted_by_owner",
                )
            ).one()
            assert deleted.after["requests_closed"] == 1
            assert deleted.after["sessions_revoked"] >= 2

    def test_the_same_number_starts_again_as_somebody_new(
        self, client: TestClient, before: dict
    ):
        again = sign_in(client, LEAVER)
        assert again["is_new_user"] is True
        assert again["user_id"] != before["first"]["user_id"]
        me = client.get("/api/v1/auth/me", headers=auth(again)).json()["data"]
        assert me["full_name"] is None
        assert me["completed_trips"] == 0

    def test_the_office_sees_an_empty_row_not_a_broken_one(
        self, client: TestClient, admin_session: dict, before: dict
    ):
        listed = client.get(
            "/api/v1/admin/users", params={"status": "DEACTIVATED"}, headers=admin_session
        )
        assert listed.status_code == 200, listed.text
        row = next(u for u in listed.json()["data"] if u["id"] == before["first"]["user_id"])
        assert row["phone"] is None and row["full_name"] is None
        # Neither switch resurrects it, and neither falls over on the NULL.
        for switch in ("suspend", "reinstate"):
            refused = client.post(
                f"/api/v1/admin/users/{row['id']}/{switch}", json={}, headers=admin_session
            )
            assert refused.status_code == 409, refused.text


# -- not yet ---------------------------------------------------------------


@pytest.fixture(scope="module")
def booked(client: TestClient, admin_session: dict) -> dict:
    """A passenger with a seat, and the driver who is coming for it."""
    passenger = auth(sign_in(client, BOOKED))
    driver, _ = road_ready_driver(client, admin_session, BOOKED_DRIVER, "DEL-0702")
    _online(client, driver)
    request_id = _ask(client, passenger)
    offered = client.post(
        f"/api/v1/driver/ride-requests/{request_id}/offer",
        headers=driver, json={"amount_minor": 25_000},
    )
    assert offered.status_code == 201, offered.text
    accepted = client.post(
        f"/api/v1/fare-offers/{offered.json()['data']['id']}/accept", headers=passenger
    )
    assert accepted.status_code == 200, accepted.text
    return {"passenger": passenger, "driver": driver, **accepted.json()["data"]}


class TestNotYet:
    def test_not_while_a_seat_is_held_for_you(self, client: TestClient, booked: dict):
        refused = client.delete("/api/v1/auth/me", headers=booked["passenger"])
        assert refused.status_code == 409, refused.text
        assert refused.json()["error"]["code"] == "ACCOUNT_HAS_ACTIVE_BOOKING"
        # Refused means untouched: she can still see her seat.
        still = client.get(f"/api/v1/bookings/{booked['booking_id']}", headers=booked["passenger"])
        assert still.status_code == 200, still.text

    def test_not_while_you_are_driving_somebody(self, client: TestClient, booked: dict):
        refused = client.delete("/api/v1/auth/me", headers=booked["driver"])
        assert refused.status_code == 409, refused.text
        assert refused.json()["error"]["code"] == "ACCOUNT_HAS_ACTIVE_TRIP"

    def test_once_the_trip_is_off_both_may_go(self, client: TestClient, booked: dict):
        called_off = client.post(
            f"/api/v1/driver/trips/{booked['trip_id']}/advance",
            headers=booked["driver"], json={"target": "CANCELLED"},
        )
        assert called_off.status_code == 200, called_off.text
        assert client.delete("/api/v1/auth/me", headers=booked["driver"]).status_code == 200

        # Her receipt outlives the driver who left: it still opens, and there
        # is simply no number to ring.
        receipt = client.get(
            f"/api/v1/bookings/{booked['booking_id']}", headers=booked["passenger"]
        )
        assert receipt.status_code == 200, receipt.text
        assert receipt.json()["data"].get("driver_phone") is None

        assert client.delete("/api/v1/auth/me", headers=booked["passenger"]).status_code == 200

    def test_not_an_account_that_opens_the_office(
        self, client: TestClient, admin_session: dict
    ):
        refused = client.delete("/api/v1/auth/me", headers=admin_session)
        assert refused.status_code == 403, refused.text
        assert refused.json()["error"]["code"] == "ACCOUNT_STAFF_UNDELETABLE"
        assert client.get("/api/v1/auth/me", headers=admin_session).status_code == 200

    def test_not_without_being_signed_in(self, client: TestClient):
        assert client.delete("/api/v1/auth/me").status_code == 401


# -- a driver leaves -----------------------------------------------------------


def test_a_driver_who_leaves_takes_his_papers_and_his_offers(
    client: TestClient, admin_session: dict
):
    from infrastructure.db.models.supply import (
        DriverDocumentRow,
        DriverRow,
        VehicleDocumentRow,
        VehicleRow,
    )
    from ui.api import deps

    driver, vehicle_id = road_ready_driver(client, admin_session, LEAVING_DRIVER, "DEL-0703")
    _online(client, driver)
    passenger = auth(sign_in(client, ASKER))
    request_id = _ask(client, passenger)
    offered = client.post(
        f"/api/v1/driver/ride-requests/{request_id}/offer",
        headers=driver, json={"amount_minor": 30_000},
    )
    assert offered.status_code == 201, offered.text
    driver_user_id = client.get("/api/v1/auth/me", headers=driver).json()["data"]["id"]

    with _db() as session:
        driver_row = session.scalars(
            select(DriverRow).where(DriverRow.user_id == driver_user_id)
        ).one()
        driver_id = driver_row.id
        papers = [
            row.file_key
            for row in session.scalars(
                select(DriverDocumentRow).where(DriverDocumentRow.driver_id == driver_id)
            ).all()
        ] + [
            row.file_key
            for row in session.scalars(
                select(VehicleDocumentRow).where(VehicleDocumentRow.vehicle_id == vehicle_id)
            ).all()
        ]
    storage = deps.file_storage()
    assert papers and all(storage.exists(key) for key in papers)

    assert client.delete("/api/v1/auth/me", headers=driver).status_code == 200

    # The tazkira, the licence, the selfie and the permit are off the disk.
    assert not any(storage.exists(key) for key in papers)
    # The passenger is no longer looking at an offer from a man who has gone.
    mine = client.get("/api/v1/ride-requests", headers=passenger).json()["data"]
    row = next(r for r in mine if r["id"] == request_id)
    assert all(offer["status"] != "OFFERED" for offer in row.get("offers", []))

    with _db() as session:
        driver_row = session.get(DriverRow, driver_id)
        assert driver_row.approval_status == "SUSPENDED"
        assert driver_row.suspended_reason == "ACCOUNT_DELETED"
        assert driver_row.availability == "OFFLINE"
        assert session.get(VehicleRow, vehicle_id).status == "RETIRED"
        assert all(
            doc.deleted_at is not None and doc.file_key == ""
            for doc in session.scalars(
                select(DriverDocumentRow).where(DriverDocumentRow.driver_id == driver_id)
            ).all()
        )

    client.post(f"/api/v1/ride-requests/{request_id}/cancel", headers=passenger)
