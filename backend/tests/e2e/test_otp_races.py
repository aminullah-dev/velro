"""The OTP limits, under requests that arrive at the same instant.

test_otp_brute_force proves the attempt counter survives a refusal when the
guesses come one after another. A script does not wait for the answer. Both
limits on sign-in were check-then-act:

  * a guess read the challenge (attempts = n), and the recorder wrote back
    attempts = n + 1. Twelve guesses that all read n = 0 were twelve
    evaluated guesses against a limit of five, and the counter ended at one;
  * a request counted the codes sent in the last minute and then created
    another. Eight requests that all counted zero were eight SMS against a
    limit of three -- each one paid for.

Real threads through the real app against a real PostgreSQL. A barrier holds
every request at the point where the race used to be -- just after the read
-- so the outcome does not depend on how the scheduler happens to interleave
them: before the fixes these failed every time, not some of the time.
"""

from __future__ import annotations

import contextlib
import threading
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.e2e.conftest import sign_in

#: Numbers no other module touches; these exhaust their limits on purpose.
PHONE_GUESSES = "+93700000584"
PHONE_REQUESTS = "+93700000585"
PHONE_DOUBLE = "+93700000586"


def _hold_after(monkeypatch, method: str, parties: int, timeout: float) -> None:
    """Make every caller of OtpRepository.<method> wait for the others.

    The barrier gives up after ``timeout``. With the fix in place a lock
    serialises the callers and they can never all arrive together; the first
    then waits out the timeout and the rest find the barrier already broken.
    """
    from infrastructure.db.repositories.identity import OtpRepository

    original = getattr(OtpRepository, method)
    barrier = threading.Barrier(parties)

    def held(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        with contextlib.suppress(threading.BrokenBarrierError):
            barrier.wait(timeout)
        return result

    monkeypatch.setattr(OtpRepository, method, held)


def _all_at_once(calls: list) -> list:
    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        futures = [pool.submit(call) for call in calls]
        return [future.result() for future in futures]


def _request_code(client: TestClient, phone: str) -> str:
    reply = client.post(
        "/api/v1/auth/otp/request", json={"phone": phone, "locale": "fa-AF"}
    )
    assert reply.status_code == 200, reply.text
    return reply.json()["data"]["debug_code"]


def _verify(client: TestClient, phone: str, code: str):
    return client.post(
        "/api/v1/auth/otp/verify",
        json={"phone": phone, "code": code, "device_id": "race", "locale": "fa-AF"},
    )


def _challenges(phone: str) -> list:
    from infrastructure.db.models.identity import OtpChallengeRow
    from ui.api import deps

    with deps._session_factory()() as session:
        return list(
            session.scalars(
                select(OtpChallengeRow).where(OtpChallengeRow.phone == phone)
            ).all()
        )


class TestTheAttemptLimitHoldsUnderConcurrency:
    def test_concurrent_wrong_codes_cannot_exceed_max_attempts(
        self, client: TestClient, monkeypatch
    ):
        real = _request_code(client, PHONE_GUESSES)
        wrong = "00000" if real != "00000" else "11111"
        guesses = 12

        _hold_after(monkeypatch, "find_active", guesses, timeout=10)
        answers = _all_at_once([lambda: _verify(client, PHONE_GUESSES, wrong)] * guesses)
        monkeypatch.undo()

        codes = [a.json()["error"]["code"] for a in answers]
        evaluated = codes.count("OTP_INVALID")
        assert evaluated <= 5, (
            f"{evaluated} of {guesses} simultaneous guesses were evaluated "
            "against a limit of 5"
        )
        assert evaluated == 5
        assert codes.count("OTP_ATTEMPTS_EXCEEDED") == guesses - 5
        remaining = sorted(
            a.json()["error"]["context"]["attempts_remaining"]
            for a in answers if a.json()["error"]["code"] == "OTP_INVALID"
        )
        assert remaining == [0, 1, 2, 3, 4]

        (challenge,) = _challenges(PHONE_GUESSES)
        assert challenge.attempts == challenge.max_attempts == 5

        # Spent is spent: the right code does not get in after the flood.
        late = _verify(client, PHONE_GUESSES, real)
        assert late.status_code == 401, late.text
        assert late.json()["error"]["code"] == "OTP_ATTEMPTS_EXCEEDED"

    def test_one_code_signs_in_once_even_when_sent_twice_at_once(
        self, client: TestClient, monkeypatch
    ):
        # A double tap on "verify", or a copy of the code used in the same
        # second: one challenge must not become two sessions. An account
        # that already exists, so the race is over the code and not over
        # creating the user.
        sign_in(client, PHONE_DOUBLE)
        real = _request_code(client, PHONE_DOUBLE)

        _hold_after(monkeypatch, "find_active", 2, timeout=10)
        answers = _all_at_once([lambda: _verify(client, PHONE_DOUBLE, real)] * 2)
        monkeypatch.undo()

        statuses = sorted(a.status_code for a in answers)
        assert statuses[0] == 200, [a.text for a in answers]
        assert statuses[1] in (401, 409), [a.text for a in answers]
        loser = next(a for a in answers if a.status_code != 200)
        assert loser.json()["error"]["code"] in (
            "OTP_ALREADY_CONSUMED", "OTP_ATTEMPTS_EXCEEDED",
        )


class TestTheRequestLimitHoldsUnderConcurrency:
    def test_concurrent_requests_cannot_exceed_max_per_window(
        self, client: TestClient, monkeypatch
    ):
        requests = 8
        _hold_after(monkeypatch, "count_recent", requests, timeout=2)
        answers = _all_at_once(
            [
                lambda: client.post(
                    "/api/v1/auth/otp/request",
                    json={"phone": PHONE_REQUESTS, "locale": "fa-AF"},
                )
            ]
            * requests
        )
        monkeypatch.undo()

        statuses = [a.status_code for a in answers]
        assert statuses.count(200) <= 3, (
            f"{statuses.count(200)} codes sent at once against a limit of 3"
        )
        assert statuses.count(200) == 3
        assert statuses.count(429) == requests - 3
        assert all(
            a.json()["error"]["code"] == "OTP_RATE_LIMITED"
            for a in answers if a.status_code == 429
        )
        assert len(_challenges(PHONE_REQUESTS)) == 3

