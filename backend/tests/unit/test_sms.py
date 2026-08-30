"""Sending the sign-in code down a real route.

Against a stubbed transport, so these cost nothing and reach nobody. What they
check is the part that no amount of testing against Twilio would settle anyway:
which sender is tried first, what happens when a route refuses, and whether the
price survives being read.
"""

from __future__ import annotations

import httpx
import pytest

from domain.afghan_networks import Network
from domain.identity import PhoneNumber
from infrastructure.services.sms import (
    FallbackSmsSender,
    TwilioSmsSender,
    _price_to_micros,
)

MTN = PhoneNumber("+93772345678")
ETISALAT = PhoneNumber("+93782345678")
AWCC = PhoneNumber("+93702345678")
CANADIAN = PhoneNumber("+13438677631")

ACCEPTED = {
    "sid": "SM0123456789abcdef",
    "num_segments": "1",
    "price": "-0.34670",
    "price_unit": "USD",
}


def transport(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def always(status: int, body: dict) -> httpx.Client:
    return transport(lambda request: httpx.Response(status, json=body))


def sender(sender_id: str = "VELRO", client: httpx.Client | None = None) -> TwilioSmsSender:
    return TwilioSmsSender(
        account_sid="AC0000000000000000000000000000000",
        auth_token="not-a-real-token",
        sender=sender_id,
        client=client or always(201, ACCEPTED),
    )


class TestSendingOne:
    def test_an_accepted_message_reports_what_it_cost(self) -> None:
        attempt = sender().attempt(
            phone=MTN, message_key="auth.sms.otp",
            payload={"code": "12345", "ttl_minutes": 5}, locale="fa-AF",
        )
        assert attempt.accepted
        assert attempt.provider_message_id == "SM0123456789abcdef"
        assert attempt.segments == 1
        assert attempt.cost_micros == 346_700
        assert attempt.cost_currency == "USD"
        assert attempt.network is Network.MTN

    def test_the_body_is_the_words_not_the_key(self) -> None:
        """An SMS reading "auth.sms.otp" costs the same as one that says
        something, and tells the person nothing."""
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(dict(httpx.QueryParams(request.content.decode())))
            return httpx.Response(201, json=ACCEPTED)

        sender(client=transport(handler)).attempt(
            phone=MTN, message_key="auth.sms.otp",
            payload={"code": "12345", "ttl_minutes": 5}, locale="fa-AF",
        )
        assert seen["Body"] == "کود ولرو شما 12345 است. تا 5 دقیقه اعتبار دارد."
        assert seen["To"] == "+93772345678"
        assert seen["From"] == "VELRO"

    def test_it_writes_in_the_language_that_was_asked_for(self) -> None:
        bodies = {}

        def handler(request: httpx.Request) -> httpx.Response:
            params = dict(httpx.QueryParams(request.content.decode()))
            bodies[params["Body"]] = True
            return httpx.Response(201, json=ACCEPTED)

        client = transport(handler)
        for locale in ("fa-AF", "ps", "en"):
            sender(client=client).attempt(
                phone=MTN, message_key="auth.sms.otp",
                payload={"code": "1", "ttl_minutes": 5}, locale=locale,
            )
        assert len(bodies) == 3, "three languages must produce three messages"

    def test_a_carrier_refusal_is_reported_not_raised(self) -> None:
        """Sign-in must fail as a message, not as a stack trace."""
        refused = sender(client=always(400, {"code": 21612, "message": "unreachable"}))
        attempt = refused.attempt(
            phone=AWCC, message_key="auth.sms.otp",
            payload={"code": "1", "ttl_minutes": 5}, locale="fa-AF",
        )
        assert not attempt.accepted
        assert attempt.error_code == "21612"
        assert "unreachable" in (attempt.error_detail or "")

    def test_no_network_from_our_side_is_told_apart_from_a_refusal(self) -> None:
        """One is ours to fix and the other is not."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route")

        attempt = sender(client=transport(handler)).attempt(
            phone=MTN, message_key="auth.sms.otp",
            payload={"code": "1", "ttl_minutes": 5}, locale="fa-AF",
        )
        assert not attempt.accepted
        assert attempt.error_code == "TRANSPORT"


class TestWhichSenderIsTriedFirst:
    """No single sender reaches every Afghan network.

    Twilio's own guidelines: AWCC will not carry an alphanumeric sender ID, and
    Etisalat, MTN, Roshan and Salaam will not carry a numeric one.
    """

    @pytest.fixture
    def chain(self) -> FallbackSmsSender:
        return FallbackSmsSender([sender("VELRO"), sender("+15550001111")])

    @pytest.mark.parametrize("phone", [MTN, ETISALAT])
    def test_ghorband_gets_the_alphanumeric_sender_first(
        self, chain: FallbackSmsSender, phone: PhoneNumber
    ) -> None:
        assert chain.order_for(phone)[0].sender == "VELRO"

    def test_awcc_gets_the_numeric_sender_first(self, chain: FallbackSmsSender) -> None:
        assert chain.order_for(AWCC)[0].sender == "+15550001111"

    def test_the_ruled_out_sender_is_moved_back_not_dropped(
        self, chain: FallbackSmsSender
    ) -> None:
        """Afghanistan permits portability, so a 070 number may be on Roshan
        today. The prefix is a preference, and removing the other sender would
        turn a wrong guess into an unreachable person."""
        assert len(chain.order_for(AWCC)) == 2
        assert len(chain.order_for(MTN)) == 2

    def test_a_foreign_number_keeps_the_configured_order(
        self, chain: FallbackSmsSender
    ) -> None:
        assert [s.sender for s in chain.order_for(CANADIAN)] == ["VELRO", "+15550001111"]


class TestTheFallback:
    def test_a_refusal_moves_to_the_next_sender(self) -> None:
        calls: list[str] = []

        def refuse_alpha(request: httpx.Request) -> httpx.Response:
            params = dict(httpx.QueryParams(request.content.decode()))
            calls.append(params["From"])
            if not params["From"].lstrip("+").isdigit():
                return httpx.Response(400, json={"code": 21612, "message": "no"})
            return httpx.Response(201, json=ACCEPTED)

        client = transport(refuse_alpha)
        chain = FallbackSmsSender([sender("VELRO", client), sender("+15550001111", client)])

        assert chain.send(
            phone=MTN, message_key="auth.sms.otp",
            payload={"code": "1", "ttl_minutes": 5}, locale="fa-AF",
        )
        assert calls == ["VELRO", "+15550001111"], "it tried the guess, then the other"

    def test_a_success_stops_the_chain(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(dict(httpx.QueryParams(request.content.decode()))["From"])
            return httpx.Response(201, json=ACCEPTED)

        client = transport(handler)
        chain = FallbackSmsSender([sender("VELRO", client), sender("+15550001111", client)])
        chain.send(
            phone=MTN, message_key="auth.sms.otp",
            payload={"code": "1", "ttl_minutes": 5}, locale="fa-AF",
        )
        assert calls == ["VELRO"], "nobody pays twice for a message that arrived"

    def test_every_attempt_is_kept_including_the_failures(self) -> None:
        """Comparing two routes is the whole point, and a chain that reports
        one boolean has thrown the evidence away."""
        chain = FallbackSmsSender(
            [
                sender("VELRO", always(400, {"code": 21612, "message": "no"})),
                sender("+15550001111", always(400, {"code": 21408, "message": "no"})),
            ]
        )
        made = chain.attempts(
            phone=MTN, message_key="auth.sms.otp",
            payload={"code": "1", "ttl_minutes": 5}, locale="fa-AF",
        )
        assert [a.error_code for a in made] == ["21612", "21408"]
        assert not any(a.accepted for a in made)

    def test_an_empty_chain_is_refused_at_construction(self) -> None:
        with pytest.raises(ValueError):
            FallbackSmsSender([])


class TestThePrice:
    """Twilio quotes five decimal places. Minor units cannot hold that, and
    float is banned anywhere near money."""

    @pytest.mark.parametrize(
        ("quoted", "micros"),
        [
            # This one is why the parse is done by hand: through float it
            # comes out 3989. About 1.5% of five-decimal prices do, always one
            # micro low, so the reconstructed bill is always a little under.
            ("-0.00399", 3_990),
            ("-0.34670", 346_700),
            ("-0.40890", 408_900),
            ("0.0075", 7_500),
            ("-1.5", 1_500_000),
            ("0", 0),
        ],
    )
    def test_it_survives_being_read(self, quoted: str, micros: int) -> None:
        assert _price_to_micros(quoted) == micros

    def test_a_missing_price_is_not_a_zero_price(self) -> None:
        """Twilio returns null until the message is priced. Recording that as
        free would understate the bill."""
        assert _price_to_micros(None) is None
        assert _price_to_micros("") is None
