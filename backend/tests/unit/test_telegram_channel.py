"""The cheap pipe, and the promise that nobody is locked out by it.

A code over Telegram costs a cent; the same code over an Afghan carrier
costs about forty-five. That difference is the whole reason this channel
exists -- and it is also the reason to be careful with it, because the
cheap pipe is the one that cannot reach a phone with no data, which in a
valley on 2G is a real person rather than an edge case.

So the rule these hold: the passenger chooses, and a choice that cannot be
delivered falls through to the carrier rather than failing.
"""

from __future__ import annotations

import httpx
import pytest

from domain.identity import PhoneNumber
from infrastructure.services.sms import TelegramGatewaySender

PHONE = PhoneNumber("+93793817977")


def sender_with(handler) -> TelegramGatewaySender:
    return TelegramGatewaySender(
        token="test-token",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def send(sender, code="12345"):
    return sender.attempt(
        phone=PHONE, message_key="auth.sms.otp",
        payload={"code": code, "ttl_minutes": 5}, locale="fa-AF",
    )


class TestDelivering:
    def test_it_sends_our_own_code_and_says_what_it_cost(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json

            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("Authorization")
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"ok": True, "result": {"request_id": "req-1"}})

        attempt = send(sender_with(handler))

        assert attempt.accepted is True
        assert seen["url"].endswith("/sendVerificationMessage")
        assert seen["auth"] == "Bearer test-token"
        # Our code, not one Telegram invented: everything that hashes and
        # checks it stays exactly as it was.
        assert seen["body"] == {"phone_number": "+93793817977", "code": "12345"}
        assert attempt.provider_message_id == "req-1"
        # A cent, in the same micro-units a carrier's price is recorded in,
        # so the two channels can be compared on one scale.
        assert attempt.cost_micros == 10_000
        assert attempt.cost_currency == "USD"


class TestRefusing:
    def test_a_number_that_is_not_on_telegram_is_a_refusal_not_a_crash(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"ok": False, "error": "PHONE_NUMBER_INVALID"})

        attempt = send(sender_with(handler))
        assert attempt.accepted is False
        assert attempt.cost_micros is None      # nothing was delivered, nothing is owed
        assert "PHONE" in (attempt.error_code or "")

    def test_the_network_falling_over_is_also_only_a_refusal(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route")

        attempt = send(sender_with(handler))
        assert attempt.accepted is False
        assert attempt.error_code == "ConnectError"

    def test_a_code_this_channel_cannot_carry_is_refused_without_a_call(self):
        # The Gateway takes 4-8 digits. If the product ever lengthens its
        # code, this must refuse rather than send something wrong -- and the
        # carrier behind it will still deliver.
        called = False

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal called
            called = True
            return httpx.Response(200, json={"ok": True})

        attempt = send(sender_with(handler), code="123456789")
        assert attempt.accepted is False
        assert called is False, "a code it cannot carry must not be sent"


@pytest.mark.parametrize("body", [
    {"ok": False, "error": "BALANCE_NOT_ENOUGH"},
    {},
    {"ok": False},
])
def test_every_shape_of_no_is_still_a_no(body):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    assert send(sender_with(handler)).accepted is False
