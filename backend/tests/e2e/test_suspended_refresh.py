"""A suspended account, and the refresh token still in its pocket.

current_actor refuses a suspended account on every request, so the access
token in a troll's phone stops working the moment the switch is thrown. The
refresh token did not. RefreshSession never looked at the account, and
suspend_user never revoked anything, so a suspended phone went on minting a
fresh access token every fifteen minutes -- each refused on arrival, but a
live session all the same, and one that came straight back the day the
account was reinstated without anybody signing in again.

These hold both halves down: suspending ends every session in the same
transaction as the suspension, and a refresh is refused for any account that
is not ACTIVE whatever state its tokens are in -- which covers the accounts
suspended before the revocation existed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from tests.e2e.conftest import sign_in

#: Numbers nothing else in the suite signs in. Each test ends or refuses every
#: session its number has, on purpose.
PHONE_SUSPENDED = "+93700000580"
PHONE_LEGACY = {"SUSPENDED": "+93700000581", "DEACTIVATED": "+93700000582"}


def _refresh(client: TestClient, token: str, device: str = "test-device"):
    return client.post(
        "/api/v1/auth/refresh", json={"refresh_token": token, "device_id": device}
    )


def _sessions_of(user_id: str) -> list:
    from infrastructure.db.models.identity import RefreshTokenRow
    from ui.api import deps

    with deps._session_factory()() as session:
        return list(
            session.scalars(
                select(RefreshTokenRow).where(RefreshTokenRow.user_id == user_id)
            ).all()
        )


def _set_status(user_id: str, status: str) -> None:
    """Behind the API's back, the way an account suspended before this fix
    looks: the status changed and every refresh token still live."""
    from infrastructure.db.models.identity import UserRow
    from ui.api import deps

    with deps._session_factory()() as session:
        session.execute(update(UserRow).where(UserRow.id == user_id).values(status=status))
        session.commit()


class TestSuspendingEndsEverySession:
    def test_suspension_revokes_the_refresh_tokens_and_refresh_refuses(
        self, client: TestClient, admin_session: dict
    ):
        # Two phones signed in to one account.
        a = sign_in(client, PHONE_SUSPENDED)
        b = sign_in(client, PHONE_SUSPENDED)
        user_id = a["user_id"]

        thrown = client.post(
            f"/api/v1/admin/users/{user_id}/suspend",
            json={"reason": "rang drivers for sport"},
            headers=admin_session,
        )
        assert thrown.status_code == 200, thrown.text

        live = [row.id for row in _sessions_of(user_id) if row.revoked_at is None]
        assert live == [], "suspending the account left its refresh tokens live"

        for session in (a, b):
            refused = _refresh(client, session["refresh_token"])
            assert refused.status_code == 401, refused.text
            assert refused.json()["error"]["code"] == "USER_SUSPENDED"

        # Reinstating does not resurrect the old sessions: the phone signs in
        # again, which is the point -- whoever held it while it was suspended
        # does not get it back for free.
        lifted = client.post(
            f"/api/v1/admin/users/{user_id}/reinstate",
            json={"reason": "warned"},
            headers=admin_session,
        )
        assert lifted.status_code == 200, lifted.text
        stale = _refresh(client, a["refresh_token"])
        assert stale.status_code == 401, stale.text
        assert sign_in(client, PHONE_SUSPENDED)["user_id"] == user_id

    def test_a_refused_suspension_revokes_nothing(
        self, client: TestClient, admin_session: dict
    ):
        # Staff cannot be suspended through this switch; the refusal must not
        # sign the administrator out on the way.
        me = client.get("/api/v1/auth/me", headers=admin_session).json()["data"]
        before = sorted(r.id for r in _sessions_of(me["id"]) if r.revoked_at is None)
        assert before

        refused = client.post(
            f"/api/v1/admin/users/{me['id']}/suspend", json={}, headers=admin_session
        )
        assert refused.status_code >= 400, refused.text

        after = sorted(r.id for r in _sessions_of(me["id"]) if r.revoked_at is None)
        assert after == before


class TestRefreshAsksTheAccount:
    @pytest.mark.parametrize("status", sorted(PHONE_LEGACY))
    def test_an_account_that_is_not_active_cannot_refresh_a_live_token(
        self, client: TestClient, status: str
    ):
        session = sign_in(client, PHONE_LEGACY[status])
        _set_status(session["user_id"], status)

        refused = _refresh(client, session["refresh_token"])
        assert refused.status_code == 401, (
            f"a {status} account rotated its refresh token: {refused.text}"
        )
        assert refused.json()["error"]["code"] == "USER_SUSPENDED"
