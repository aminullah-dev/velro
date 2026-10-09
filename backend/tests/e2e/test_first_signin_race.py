"""Two first sign-ins for one new number, at the same instant.

The account is created on the first successful code, by a lookup followed by
an insert. Two sign-ins for a number nobody has used yet -- the person taps
"resend", the first code arrives late, and both are typed on two handsets or
in two tabs -- both looked, both found nobody, and both inserted. The unique
constraint on the phone kept the data right and turned the second sign-in
into a 500, on the one request a brand-new user must never see fail.

Each sign-in uses its own code, so the race is over creating the user and
not over the code (test_otp_races covers that one). A barrier holds both
just after the lookup that used to decide it.
"""

from __future__ import annotations

import contextlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import func, select

PHONE = "+93700000589"


def _request_code(client: TestClient) -> str:
    reply = client.post("/api/v1/auth/otp/request", json={"phone": PHONE, "locale": "fa-AF"})
    assert reply.status_code == 200, reply.text
    return reply.json()["data"]["debug_code"]


def _verify(client: TestClient, code: str, device: str):
    return client.post(
        "/api/v1/auth/otp/verify",
        json={"phone": PHONE, "code": code, "device_id": device, "locale": "fa-AF"},
    )


def test_two_first_sign_ins_make_one_account_and_two_sessions(
    client: TestClient, monkeypatch
) -> None:
    from infrastructure.db.models.identity import RoleRow, UserRoleRow, UserRow
    from infrastructure.db.repositories.identity import UserRepository
    from ui.api import deps

    barrier = threading.Barrier(2)
    held = {"calls": 0}
    guard = threading.Lock()
    original = UserRepository.find_by_phone

    def find_then_wait(self, phone):
        row = original(self, phone)
        with guard:
            held["calls"] += 1
            first_two = held["calls"] <= 2
        if first_two and phone == PHONE:
            with contextlib.suppress(threading.BrokenBarrierError):
                barrier.wait(10)
        return row

    monkeypatch.setattr(UserRepository, "find_by_phone", find_then_wait)

    first_code = _request_code(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(_verify, client, first_code, "handset-a")
        # The first sign-in has taken its code and looked for the account.
        # Only now is the second code asked for, so each sign-in holds a
        # challenge of its own.
        deadline = time.monotonic() + 10
        while barrier.n_waiting < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert barrier.n_waiting == 1, "the first sign-in never reached the lookup"
        second = pool.submit(_verify, client, _request_code(client), "handset-b")
        answers = [first.result(), second.result()]
    monkeypatch.undo()

    assert [a.status_code for a in answers] == [200, 200], [a.text for a in answers]
    users = {a.json()["data"]["user_id"] for a in answers}
    assert len(users) == 1, "one number, one account"
    # Both handsets hold a working session of their own.
    for answer in answers:
        token = answer.json()["data"]["access_token"]
        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200, me.text

    with deps._session_factory()() as session:
        assert session.scalar(
            select(func.count()).select_from(UserRow).where(UserRow.phone == PHONE)
        ) == 1
        (user_id,) = users
        roles = session.scalars(
            select(RoleRow.code)
            .join(UserRoleRow, UserRoleRow.role_id == RoleRow.id)
            .where(UserRoleRow.user_id == user_id, UserRoleRow.deleted_at.is_(None))
        ).all()
        assert roles == ["PASSENGER"]
