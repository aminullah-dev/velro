"""The off switch, thrown and un-thrown through the front door.

Suspension is the backstop behind every other defence: the geofence prices
out boredom and the SIM prices out identity, but whatever slips past both
ends here -- one tap, and the account is off *now*, because the actor is
re-read from the users table on every request rather than trusted from the
token.

A dedicated number, signed in once. Nothing else in the suite touches it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import auth, sign_in

TROLL_PHONE = "+93700000558"


@pytest.fixture(scope="module")
def troll(client: TestClient) -> dict:
    return auth(sign_in(client, TROLL_PHONE))


def _find_user_id(client: TestClient, admin: dict, phone: str) -> str:
    found = client.get(
        "/api/v1/admin/users", params={"phone": phone[-9:]}, headers=admin
    )
    assert found.status_code == 200, found.text
    rows = found.json()["data"]
    assert len(rows) == 1, rows
    return rows[0]["id"]


class TestTheSwitch:
    def test_suspended_means_now_not_at_token_expiry(
        self, client: TestClient, admin_session: dict, troll: dict
    ):
        user_id = _find_user_id(client, admin_session, TROLL_PHONE)

        thrown = client.post(
            f"/api/v1/admin/users/{user_id}/suspend",
            json={"reason": "rang drivers for sport"},
            headers=admin_session,
        )
        assert thrown.status_code == 200, thrown.text
        assert thrown.json()["data"]["status"] == "SUSPENDED"

        # The token in his pocket is still cryptographically valid. It no
        # longer opens anything.
        refused = client.get("/api/v1/bookings", headers=troll)
        assert refused.status_code == 401, refused.text
        assert refused.json()["error"]["code"] == "USER_SUSPENDED"

    def test_a_fresh_sign_in_is_refused_too(self, client: TestClient):
        requested = client.post(
            "/api/v1/auth/otp/request", json={"phone": TROLL_PHONE, "locale": "fa-AF"}
        )
        assert requested.status_code == 200, requested.text
        verified = client.post(
            "/api/v1/auth/otp/verify",
            json={
                "phone": TROLL_PHONE,
                "code": requested.json()["data"]["debug_code"],
                "device_id": "test-device",
                "locale": "fa-AF",
            },
        )
        assert verified.status_code == 401, verified.text
        assert verified.json()["error"]["code"] == "USER_SUSPENDED"

    def test_suspending_twice_is_a_conflict_not_a_shrug(
        self, client: TestClient, admin_session: dict
    ):
        user_id = _find_user_id(client, admin_session, TROLL_PHONE)
        again = client.post(
            f"/api/v1/admin/users/{user_id}/suspend",
            json={}, headers=admin_session,
        )
        assert again.status_code == 409, again.text
        assert again.json()["error"]["code"] == "USER_ALREADY_SUSPENDED"

    def test_reinstated_means_now_as_well(
        self, client: TestClient, admin_session: dict, troll: dict
    ):
        user_id = _find_user_id(client, admin_session, TROLL_PHONE)
        lifted = client.post(
            f"/api/v1/admin/users/{user_id}/reinstate",
            json={"reason": "first offence, warned"},
            headers=admin_session,
        )
        assert lifted.status_code == 200, lifted.text

        # The same old token works again: nothing was revoked, only refused.
        allowed = client.get("/api/v1/bookings", headers=troll)
        assert allowed.status_code == 200, allowed.text

    def test_reinstating_an_active_account_is_refused(
        self, client: TestClient, admin_session: dict
    ):
        user_id = _find_user_id(client, admin_session, TROLL_PHONE)
        pointless = client.post(
            f"/api/v1/admin/users/{user_id}/reinstate",
            json={}, headers=admin_session,
        )
        assert pointless.status_code == 409, pointless.text
        assert pointless.json()["error"]["code"] == "USER_NOT_SUSPENDED"


class TestTheDoorFromInside:
    def test_staff_cannot_be_suspended_through_this_switch(
        self, client: TestClient, admin_session: dict
    ):
        # The admin looks himself up and throws the switch at his own account.
        me = client.get("/api/v1/auth/me", headers=admin_session)
        assert me.status_code == 200, me.text
        my_id = me.json()["data"]["id"]

        refused = client.post(
            f"/api/v1/admin/users/{my_id}/suspend",
            json={"reason": "testing the lock"},
            headers=admin_session,
        )
        assert refused.status_code == 403, refused.text
        assert refused.json()["error"]["code"] == "PERMISSION_DENIED"

    def test_a_passenger_cannot_reach_the_switch_at_all(
        self, client: TestClient, admin_session: dict, troll: dict
    ):
        user_id = _find_user_id(client, admin_session, TROLL_PHONE)
        refused = client.post(
            f"/api/v1/admin/users/{user_id}/suspend",
            json={}, headers=troll,
        )
        assert refused.status_code == 403, refused.text
