"""The attempt counter, and the transaction that used to eat it.

A wrong code answers 401. The session middleware commits only on responses
under 400, so the increment that the domain had just made was rolled back
with the refusal -- and three wrong codes in a row each answered "4 attempts
remaining" while the database sat at zero. A five-digit code with no
attempt limit is not a code; it is a delay.

These hold the counter down. If they ever fail, sign-in has become
guessable, and sign-in is the whole product.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

#: A number per test, and none of them shared with another module.
#:
#: Two reasons. These tests exhaust challenges on purpose, which would break
#: any module that signs the same persona in; and asking for codes is itself
#: rate-limited to three per minute, so tests that share a number start
#: failing on the limiter rather than on what they are about.
PHONE_COUNTER = "+93700000556"
PHONE_EXHAUST = "+93700000557"
PHONE_FRESH = "+93700000559"
PHONE_MIXED = "+93700000560"


def _request_code(client: TestClient, phone: str) -> str:
    reply = client.post(
        "/api/v1/auth/otp/request", json={"phone": phone, "locale": "fa-AF"}
    )
    assert reply.status_code == 200, reply.text
    code = reply.json()["data"]["debug_code"]
    assert code, "development build must echo the code"
    return code


def _guess(client: TestClient, phone: str, code: str):
    return client.post(
        "/api/v1/auth/otp/verify",
        json={"phone": phone, "code": code, "device_id": "brute", "locale": "fa-AF"},
    )


def _wrong_for(real: str) -> str:
    return "00000" if real != "00000" else "11111"


class TestTheCounterSurvivesTheRefusal:
    def test_each_wrong_code_costs_an_attempt(self, client: TestClient):
        real = _request_code(client, PHONE_COUNTER)
        wrong = _wrong_for(real)

        seen = []
        for _ in range(3):
            answer = _guess(client, PHONE_COUNTER, wrong)
            assert answer.status_code == 401, answer.text
            body = answer.json()["error"]
            assert body["code"] == "OTP_INVALID"
            seen.append(body["context"]["attempts_remaining"])

        # The whole point: 4, 3, 2 -- not 4, 4, 4.
        assert seen == [4, 3, 2], (
            "the attempt counter was rolled back with the refusal that "
            "reported it"
        )

    def test_a_spent_challenge_refuses_even_the_right_code(self, client: TestClient):
        real = _request_code(client, PHONE_EXHAUST)
        wrong = _wrong_for(real)

        for _ in range(5):
            assert _guess(client, PHONE_EXHAUST, wrong).status_code == 401

        spent = _guess(client, PHONE_EXHAUST, wrong)
        assert spent.json()["error"]["code"] == "OTP_ATTEMPTS_EXCEEDED"

        # Fails closed. Whoever was guessing does not get in by finally
        # guessing right, and the owner asks for a new code.
        refused = _guess(client, PHONE_EXHAUST, real)
        assert refused.status_code == 401, refused.text
        assert refused.json()["error"]["code"] == "OTP_ATTEMPTS_EXCEEDED"


class TestTheHonestPathStillWorks:
    def test_a_fresh_code_after_an_exhausted_one_signs_in(self, client: TestClient):
        # The defence must not lock a real person out of their own phone:
        # a new challenge starts clean.
        real = _request_code(client, PHONE_FRESH)
        session = _guess(client, PHONE_FRESH, real)
        assert session.status_code == 200, session.text
        assert session.json()["data"]["access_token"]

    def test_one_wrong_guess_does_not_spoil_the_next_correct_one(
        self, client: TestClient
    ):
        real = _request_code(client, PHONE_MIXED)
        wrong = _wrong_for(real)
        assert _guess(client, PHONE_MIXED, wrong).status_code == 401
        assert _guess(client, PHONE_MIXED, real).status_code == 200
