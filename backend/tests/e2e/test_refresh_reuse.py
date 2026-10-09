"""Refresh-token reuse, and the transaction that used to forgive it.

Refresh tokens rotate: each one is good for exactly one refresh. A token that
is presented a second time has therefore been copied, and RefreshSession
treats that as theft -- it refuses the replay and revokes every session the
user has, so whoever holds the other copy is cut off too.

The refusal is a 401, and the session middleware commits only responses under
400. So the revocation was written and then rolled back with the very answer
that reported it: the replay failed, but the thief's session -- and every other
one -- carried on refreshing. The same trap the OTP attempt counter fell into
(test_otp_brute_force.py), on the other half of sign-in.

These hold the revocation down. If they ever fail, a stolen refresh token is
good until it expires, whatever the owner does.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.e2e.conftest import sign_in

#: A number per test, shared with no other module: signing in twice is two of
#: the three codes a minute the limiter allows, and these tests end every
#: session the number has on purpose.
PHONE_REPLAY = "+93700000570"
PHONE_HONEST = "+93700000571"


def _refresh(client: TestClient, token: str, device: str):
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


class TestAReplayEndsEverySession:
    def test_a_replayed_token_revokes_the_other_sessions_too(self, client: TestClient):
        # Two devices: the owner's phone (A) and, say, a thief's copy (B).
        a = sign_in(client, PHONE_REPLAY)
        b = sign_in(client, PHONE_REPLAY)
        assert a["user_id"] == b["user_id"]

        # A refreshes, as a phone does every fifteen minutes. Its old token is
        # now spent and has a successor.
        rotated = _refresh(client, a["refresh_token"], "device-a")
        assert rotated.status_code == 200, rotated.text
        a2 = rotated.json()["data"]["refresh_token"]

        # Somebody presents A's spent token again: refused, as theft.
        replay = _refresh(client, a["refresh_token"], "device-a")
        assert replay.status_code == 401, replay.text
        assert replay.json()["error"]["code"] == "REFRESH_TOKEN_REVOKED"

        # The whole point: the refusal did not take the revocation with it.
        # Every session this user had is over in the database...
        rows = _sessions_of(a["user_id"])
        assert len(rows) == 3  # A, A's successor, B
        live = [row.id for row in rows if row.revoked_at is None]
        assert live == [], (
            "the reuse revocation was rolled back with the 401 that reported it"
        )

        # ...and in practice: neither B nor A's fresh successor refreshes.
        for token, device in ((b["refresh_token"], "device-b"), (a2, "device-a")):
            refused = _refresh(client, token, device)
            assert refused.status_code == 401, refused.text
            assert refused.json()["error"]["code"] == "REFRESH_TOKEN_REVOKED"


class TestTheHonestPathStillWorks:
    def test_rotation_alone_leaves_the_other_session_alone(self, client: TestClient):
        # A refresh is not a replay: the other device must not be signed out
        # because this one rotated.
        a = sign_in(client, PHONE_HONEST)
        b = sign_in(client, PHONE_HONEST)

        rotated = _refresh(client, a["refresh_token"], "device-a")
        assert rotated.status_code == 200, rotated.text

        again = _refresh(client, b["refresh_token"], "device-b")
        assert again.status_code == 200, again.text

        live = [row for row in _sessions_of(a["user_id"]) if row.revoked_at is None]
        assert len(live) == 2  # A's successor and B's
