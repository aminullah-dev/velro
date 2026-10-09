"""Two refreshes of one token at the same instant.

Rotation read the token, saw it unrevoked, minted a successor and marked the
old one revoked -- with nothing stopping a second request that read the same
row a moment earlier from doing exactly the same. Both answered 200, and one
refresh token had become two live chains. Whoever copied the token only had
to race the owner's phone to keep a session that reuse detection never sees.

Both apps already serialise their own refreshes (an @Synchronized
authenticator on Android, one shared Task on iOS), so two presentations of
one token at once are not something an honest phone does. They are treated
exactly as a replay one second later would be: refused, and every session of
the account ended.
"""

from __future__ import annotations

import contextlib
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.e2e.conftest import sign_in

PHONE = "+93700000590"


def test_a_token_refreshed_twice_at_once_does_not_fork(
    client: TestClient, monkeypatch
) -> None:
    from infrastructure.db.models.identity import RefreshTokenRow
    from infrastructure.db.repositories.identity import RefreshTokenRepository
    from ui.api import deps

    session = sign_in(client, PHONE)

    # Hold both requests just after they read the token, where the race was.
    original = RefreshTokenRepository.find_by_hash
    barrier = threading.Barrier(2)

    def held(self, token_hash):
        row = original(self, token_hash)
        with contextlib.suppress(threading.BrokenBarrierError):
            barrier.wait(10)
        return row

    monkeypatch.setattr(RefreshTokenRepository, "find_by_hash", held)

    def refresh():
        return client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": session["refresh_token"], "device_id": "race"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        answers = [f.result() for f in [pool.submit(refresh), pool.submit(refresh)]]
    monkeypatch.undo()

    statuses = sorted(a.status_code for a in answers)
    assert statuses == [200, 401], [a.text for a in answers]
    loser = next(a for a in answers if a.status_code == 401)
    assert loser.json()["error"]["code"] == "REFRESH_TOKEN_REVOKED"

    with deps._session_factory()() as db:
        live = db.scalars(
            select(RefreshTokenRow).where(
                RefreshTokenRow.user_id == session["user_id"],
                RefreshTokenRow.revoked_at.is_(None),
            )
        ).all()
    assert live == [], f"{len(live)} refresh chain(s) survived a raced rotation"
