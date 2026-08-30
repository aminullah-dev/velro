"""Sending a text message through a real network.

The only way into VELRO is a code in an SMS, so this is the front door for
everybody in Ghorband. It is also the only meaningful running cost: at the
rates quoted for Afghan operators a sign-in is roughly a third of a dollar,
which is more than a day of the server.

Two senders here and a third that chains them. The chain is not decoration.
Afghanistan's routes disagree about what a sender may be -- AWCC will not take
an alphanumeric sender ID, and Etisalat, MTN, Roshan and Salaam will not take a
numeric one -- so no single configuration reaches everybody. Worse, the prefix
that tells you which network a number is on records the original allocation,
and Afghanistan permits portability. There is no way to be sure in advance. So
the order is a guess and the fallback is what makes the guess safe.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from domain.afghan_networks import Network, likely_network
from domain.identity import PhoneNumber
from shared.i18n import render
from shared.logging import get_logger

log = get_logger(__name__)

TWILIO_API = "https://api.twilio.com/2010-04-01"

# Which sender each Afghan network's route will carry, per Twilio's own
# Afghanistan guidelines. A fact about a route, not about Afghanistan, so it
# lives here beside the adapter rather than in the domain -- a second provider
# may route differently and would bring its own table.
_REFUSES_ALPHANUMERIC = frozenset({Network.AWCC})


@dataclass(frozen=True)
class Attempt:
    """What happened, in enough detail to compare two providers on evidence."""

    provider: str
    sender: str
    accepted: bool
    latency_ms: int
    network: Network | None = None
    provider_message_id: str | None = None
    segments: int | None = None
    # Micro-units of the major unit, not minor ones. The house rule is minor
    # units because a fare is charged in whole afghani; a carrier price is
    # quoted at five decimal places -- $0.34670 -- and rounding it to cents
    # loses a third of it. Still an integer, so the ban on floats holds.
    cost_micros: int | None = None
    cost_currency: str | None = None
    error_code: str | None = None
    error_detail: str | None = None


class TwilioSmsSender:
    """One Twilio account, one sender.

    Deliberately not the official SDK. This makes one HTTP call with three form
    fields, and a dependency that ships its own HTTP client, retry policy and
    logging is a lot of surface for that -- surface that would sit in the
    sign-in path of the whole product.
    """

    def __init__(
        self,
        *,
        account_sid: str,
        auth_token: str,
        sender: str,
        api_key_sid: str | None = None,
        client: httpx.Client | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._sender = sender
        # Twilio accepts two credential shapes, and they are not interchangeable
        # in the way the first version of this assumed.
        #
        # With the account's own Auth Token, the username IS the account SID, so
        # one value serves both the URL path and the auth pair. With an API key
        # -- which is what production should use, because it can be revoked
        # without rotating the whole account's password -- the username is the
        # key's own SK... sid and the URL still needs the AC... account sid.
        #
        # Sending both as one value fails with 20003 Authenticate, and it fails
        # identically whether the mistake is a wrong password or a mismatched
        # pair, which is what made this take a while to see on a live server.
        self._auth_user = api_key_sid or account_sid
        self._client = client
        self._timeout = timeout_seconds

    @property
    def name(self) -> str:
        return f"twilio:{self._sender}"

    @property
    def sender(self) -> str:
        return self._sender

    @property
    def is_alphanumeric(self) -> bool:
        return not self._sender.lstrip("+").isdigit()

    def attempt(
        self,
        *,
        phone: PhoneNumber,
        message_key: str,
        payload: dict[str, Any],
        locale: str,
    ) -> Attempt:
        body = render(message_key, locale=locale, **payload)
        network = likely_network(phone.value)
        started = time.monotonic()

        def elapsed() -> int:
            return int((time.monotonic() - started) * 1000)

        try:
            client = self._client or httpx.Client(timeout=self._timeout)
            response = client.post(
                f"{TWILIO_API}/Accounts/{self._account_sid}/Messages.json",
                auth=(self._auth_user, self._auth_token),
                data={"To": phone.value, "From": self._sender, "Body": body},
            )
        except httpx.HTTPError as error:
            # No network from the server, not a refusal by the carrier. Worth
            # distinguishing: the first is ours to fix and the second is not.
            return Attempt(
                provider=self.name,
                sender=self._sender,
                accepted=False,
                latency_ms=elapsed(),
                network=network,
                error_code="TRANSPORT",
                error_detail=type(error).__name__,
            )

        latency = elapsed()
        try:
            document = response.json()
        except ValueError:
            document = {}

        if response.status_code >= 400:
            return Attempt(
                provider=self.name,
                sender=self._sender,
                accepted=False,
                latency_ms=latency,
                network=network,
                error_code=str(document.get("code") or response.status_code),
                error_detail=str(document.get("message") or "")[:300],
            )

        return Attempt(
            provider=self.name,
            sender=self._sender,
            accepted=True,
            latency_ms=latency,
            network=network,
            provider_message_id=document.get("sid"),
            segments=_as_int(document.get("num_segments")),
            cost_micros=_price_to_micros(document.get("price")),
            cost_currency=document.get("price_unit"),
        )

    def send(
        self,
        *,
        phone: PhoneNumber,
        message_key: str,
        payload: dict[str, Any],
        locale: str,
    ) -> bool:
        return self.attempt(
            phone=phone, message_key=message_key, payload=payload, locale=locale
        ).accepted


class FallbackSmsSender:
    """Tries each sender in turn, best guess first.

    The ordering is the only place the network prefix is used, and it is used
    as a preference rather than a rule: a number that has been ported is
    indistinguishable from one that has not, so the sender the prefix rules out
    is moved to the back of the queue instead of being removed from it.

    A sender that refuses is not the end. A sender that succeeds is.
    """

    name = "fallback"

    def __init__(self, senders: list[TwilioSmsSender]) -> None:
        if not senders:
            raise ValueError("a fallback chain with no senders delivers nothing")
        self._senders = senders

    def order_for(self, phone: PhoneNumber) -> list[TwilioSmsSender]:
        network = likely_network(phone.value)
        if network is None:
            return list(self._senders)

        def unwanted(sender: TwilioSmsSender) -> bool:
            """Whether this network's route is known to refuse this sender."""
            if network in _REFUSES_ALPHANUMERIC:
                return sender.is_alphanumeric
            # Every other Afghan network prohibits a numeric sender.
            return not sender.is_alphanumeric

        return sorted(self._senders, key=unwanted)

    def attempts(
        self,
        *,
        phone: PhoneNumber,
        message_key: str,
        payload: dict[str, Any],
        locale: str,
    ) -> list[Attempt]:
        """Every attempt made, in order, including the ones that failed.

        Returned rather than only the outcome, because comparing providers is
        the point and a chain that reports one boolean throws away the evidence.
        """
        made: list[Attempt] = []
        for sender in self.order_for(phone):
            attempt = sender.attempt(
                phone=phone, message_key=message_key, payload=payload, locale=locale
            )
            made.append(attempt)
            if attempt.accepted:
                break
        return made

    def send(
        self,
        *,
        phone: PhoneNumber,
        message_key: str,
        payload: dict[str, Any],
        locale: str,
    ) -> bool:
        made = self.attempts(
            phone=phone, message_key=message_key, payload=payload, locale=locale
        )
        accepted = any(attempt.accepted for attempt in made)

        for attempt in made:
            if not attempt.accepted:
                continue
            # The provider's message id, which is the only handle anybody has
            # on a message after it leaves here.
            #
            # Without this line a sent message is unfindable: the carrier
            # decides delivery minutes later and asynchronously, and the only
            # way to ask what happened is to name the message. Discovered while
            # testing the first real Afghan numbers -- the sends succeeded, and
            # there was no way to learn whether either arrived, because nothing
            # had written down what to look up.
            #
            # Never the code, never the body, never the unmasked number: this
            # is an operational breadcrumb, not a copy of the message.
            log.info(
                "sms.accepted",
                phone=phone.masked,
                message_key=message_key,
                provider=attempt.provider,
                message_id=attempt.provider_message_id,
                network=attempt.network.value if attempt.network else None,
                segments=attempt.segments,
                cost_micros=attempt.cost_micros,
                latency_ms=attempt.latency_ms,
            )

        if not accepted:
            log.error(
                "sms.every_route_refused",
                phone=phone.masked,
                message_key=message_key,
                attempts=[
                    {"provider": a.provider, "error_code": a.error_code} for a in made
                ],
            )
        return accepted


def _as_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _price_to_micros(price: object) -> int | None:
    """Twilio quotes a negative decimal string: "-0.34670".

    Parsed by hand rather than through float, which is banned in any path that
    touches money. Not a formality here: over the five-decimal prices a carrier
    actually quotes, `int(float(price) * 1_000_000)` is one micro low for about
    1.5% of them, and always low -- so the bill it reconstructs is always a
    little smaller than the bill that arrives.
    """
    if price is None:
        return None
    text = str(price).strip().lstrip("-")
    if not text:
        return None
    whole, _, fraction = text.partition(".")
    fraction = (fraction + "000000")[:6]
    if not whole.isdigit() or not fraction.isdigit():
        return None
    return int(whole) * 1_000_000 + int(fraction)
