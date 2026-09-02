"""The SMTP adapter, against a fake server.

What matters is that the message is the right message, in the right
language, sent over an upgraded connection, and that a server that refuses
is reported as a refusal rather than a crash -- the use case behind this has
a carrier to fall through to, and only if it hears "no".
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass, field
from typing import Any

from infrastructure.services.email import SmtpEmailSender, mask_email


@dataclass
class FakeSmtp:
    """Just enough of smtplib.SMTP to see what was done with it."""

    host: str
    port: int
    timeout: float
    tls_started: bool = False
    logins: list[tuple[str, str]] = field(default_factory=list)
    messages: list[Any] = field(default_factory=list)
    refuse_with: Exception | None = None

    def __enter__(self) -> FakeSmtp:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def starttls(self) -> None:
        self.tls_started = True

    def login(self, username: str, password: str) -> None:
        self.logins.append((username, password))

    def send_message(self, message: Any) -> None:
        if self.refuse_with is not None:
            raise self.refuse_with
        self.messages.append(message)


class Transport:
    def __init__(self, **preset: Any) -> None:
        self.preset = preset
        self.made: list[FakeSmtp] = []

    def __call__(self, host: str, port: int, *, timeout: float) -> FakeSmtp:
        smtp = FakeSmtp(host=host, port=port, timeout=timeout, **self.preset)
        self.made.append(smtp)
        return smtp


def _sender(transport: Transport, port: int = 587) -> SmtpEmailSender:
    return SmtpEmailSender(
        host="smtp.example.org", port=port, username="ops@example.org",
        password="app-password", sender="VELRO <ops@example.org>", transport=transport,
    )


PAYLOAD = {"code": "13579", "ttl_minutes": 5}


class TestTheMessage:
    def test_carries_the_code_in_the_readers_language(self) -> None:
        transport = Transport()
        accepted = _sender(transport).send(
            to="owner@example.org", subject_key="auth.email.otp_subject",
            message_key="auth.email.otp", payload=PAYLOAD, locale="fa-AF",
        )
        assert accepted
        [smtp] = transport.made
        [message] = smtp.messages
        assert message["To"] == "owner@example.org"
        assert message["From"] == "VELRO <ops@example.org>"
        assert "ولرو" in message["Subject"]
        body = message.get_content()
        assert "13579" in body
        assert "۵" not in body and "5" in body, "the ttl is a placeholder, rendered as given"

    def test_in_english_when_asked(self) -> None:
        transport = Transport()
        _sender(transport).send(
            to="owner@example.org", subject_key="auth.email.otp_subject",
            message_key="auth.email.otp", payload=PAYLOAD, locale="en",
        )
        assert transport.made[0].messages[0]["Subject"] == "Your VELRO sign-in code"


class TestTheConnection:
    def test_upgrades_to_tls_and_logs_in(self) -> None:
        transport = Transport()
        _sender(transport).send(
            to="a@b.c", subject_key="auth.email.otp_subject",
            message_key="auth.email.otp", payload=PAYLOAD, locale="en",
        )
        [smtp] = transport.made
        assert smtp.host == "smtp.example.org" and smtp.port == 587
        assert smtp.tls_started, "a code must not cross the wire in the clear"
        assert smtp.logins == [("ops@example.org", "app-password")]

    def test_implicit_tls_on_465_skips_starttls(self) -> None:
        transport = Transport()
        _sender(transport, port=465).send(
            to="a@b.c", subject_key="auth.email.otp_subject",
            message_key="auth.email.otp", payload=PAYLOAD, locale="en",
        )
        assert not transport.made[0].tls_started


class TestARefusal:
    def test_is_reported_not_raised(self) -> None:
        transport = Transport(refuse_with=smtplib.SMTPAuthenticationError(535, b"bad password"))
        accepted = _sender(transport).send(
            to="a@b.c", subject_key="auth.email.otp_subject",
            message_key="auth.email.otp", payload=PAYLOAD, locale="en",
        )
        assert accepted is False

    def test_a_dead_network_is_a_refusal_too(self) -> None:
        transport = Transport(refuse_with=OSError("connection refused"))
        assert not _sender(transport).send(
            to="a@b.c", subject_key="auth.email.otp_subject",
            message_key="auth.email.otp", payload=PAYLOAD, locale="en",
        )


def test_the_log_never_carries_the_whole_address() -> None:
    assert mask_email("aminullah@example.org") == "a***@example.org"
    assert mask_email("nonsense") == "***"
