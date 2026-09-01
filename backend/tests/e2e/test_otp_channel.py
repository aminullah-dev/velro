"""Choosing where the code arrives, and never being locked out by the choice.

The operator's reasoning, and it is right: with a thousand users at least a
hundred are on Telegram, and a cent instead of forty-five cents for those
hundred is the difference between a budget that lasts a month and one that
lasts a year. So the passenger picks.

What must not happen is that picking the cheap channel locks somebody out.
These hold the fallback in place: a Telegram request that cannot be
delivered still puts a code on the phone, and the answer says which app to
look in.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

#: Numbers of their own: these ask for codes repeatedly and the request
#: limiter is three a minute per number.
PHONE_SMS = "+93700000561"
PHONE_TELEGRAM = "+93700000562"


def _ask(client: TestClient, phone: str, channel: str | None = None):
    body = {"phone": phone, "locale": "fa-AF"}
    if channel is not None:
        body["channel"] = channel
    return client.post("/api/v1/auth/otp/request", json=body)


class TestTheChoiceReachesTheServer:
    def test_asking_for_sms_gets_sms(self, client: TestClient):
        answer = _ask(client, PHONE_SMS, "sms")
        assert answer.status_code == 200, answer.text
        assert answer.json()["data"]["channel"] == "sms"

    def test_the_default_is_sms(self, client: TestClient):
        # The channel that reaches a phone with no data at all. A default
        # that fails is worse than a default that costs more.
        answer = _ask(client, PHONE_SMS)
        assert answer.json()["data"]["channel"] == "sms"

    def test_a_channel_nobody_offers_is_refused_not_guessed(self, client: TestClient):
        answer = _ask(client, PHONE_SMS, "carrier-pigeon")
        assert answer.status_code == 422, answer.text


class TestNobodyIsLockedOutByTheCheapPipe:
    def test_asking_for_telegram_without_an_account_still_delivers(
        self, client: TestClient
    ):
        """The state every deployment starts in.

        No Telegram token configured, so the channel does not exist. Asking
        for it must not fail -- it must quietly become an SMS and say so.
        """
        answer = _ask(client, PHONE_TELEGRAM, "telegram")
        assert answer.status_code == 200, answer.text
        assert answer.json()["data"]["channel"] == "sms", (
            "a Telegram request with no Telegram configured must fall through "
            "to the carrier, not fail"
        )

    def test_the_code_still_works_after_falling_through(self, client: TestClient):
        asked = _ask(client, PHONE_TELEGRAM, "telegram")
        code = asked.json()["data"]["debug_code"]
        assert code, "development build must echo the code"

        signed_in = client.post(
            "/api/v1/auth/otp/verify",
            json={"phone": PHONE_TELEGRAM, "code": code,
                  "device_id": "channel-test", "locale": "fa-AF"},
        )
        assert signed_in.status_code == 200, signed_in.text
        assert signed_in.json()["data"]["access_token"]
