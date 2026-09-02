"""Sending a sign-in code by email.

For the staff console only. The handsets sign in by SMS or Telegram because
that is what a phone in Ghorband can receive; the console is opened from a
laptop by the handful of people who run the service, and for them an inbox
is both free -- an Afghan carrier charges nearly half a dollar a code -- and
reachable from anywhere, which a Roshan SIM in a drawer in Parwan is not.

One SMTP conversation per message, over STARTTLS, with the standard library.
The same shape as the SMS adapters: a message key and a payload, rendered
here in the reader's language, and a boolean back. False means "this pipe
did not carry it", and the caller falls through to one that will.
"""

from __future__ import annotations

import smtplib
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any

from shared.i18n import render
from shared.logging import get_logger

log = get_logger(__name__)


def mask_email(address: str) -> str:
    """a***@example.org -- enough to recognise, not enough to reuse."""
    local, _, domain = address.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


class SmtpEmailSender:
    name = "smtp"

    def __init__(
        self,
        *,
        host: str,
        sender: str,
        port: int = 587,
        username: str = "",
        password: str = "",
        timeout_seconds: float = 15.0,
        #: The connection factory. Tests hand in a fake; nothing else does.
        transport: Callable[..., Any] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._timeout = timeout_seconds
        self._transport = transport

    def send(
        self,
        *,
        to: str,
        subject_key: str,
        message_key: str,
        payload: dict[str, Any],
        locale: str,
    ) -> bool:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = to
        message["Subject"] = render(subject_key, locale=locale, **payload)
        message.set_content(render(message_key, locale=locale, **payload))

        try:
            with self._connect() as smtp:
                if self._port != 465:
                    # Implicit TLS on 465; everything else upgrades in place.
                    # A server that refuses STARTTLS is a server the code
                    # must not be sent through in the clear.
                    smtp.starttls()
                if self._username:
                    smtp.login(self._username, self._password)
                smtp.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            # A refusal, not a crash: the caller has a carrier behind this.
            log.warning(
                "email.failed",
                to=mask_email(to),
                message_key=message_key,
                error=type(exc).__name__,
                detail=str(exc)[:200],
            )
            return False

        # Never the code, never the body. An operational breadcrumb only.
        log.info("email.accepted", to=mask_email(to), message_key=message_key)
        return True

    def _connect(self) -> Any:
        factory = self._transport
        if factory is None:
            factory = smtplib.SMTP_SSL if self._port == 465 else smtplib.SMTP
        return factory(self._host, self._port, timeout=self._timeout)
