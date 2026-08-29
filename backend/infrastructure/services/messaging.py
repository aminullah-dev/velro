"""Notification delivery.

Two channels behind one interface. Push is the default; SMS is the fallback for
the many devices in this market that have no reliable push connection. Both
carry a message *key* and a payload -- never a rendered sentence -- so the
device renders it in the locale the person is actually reading.

The console implementations are what development and CI use. A real provider is
a third implementation of the same protocol and touches nothing else.
"""

from __future__ import annotations

from typing import Any

from domain.identity import PhoneNumber
from shared.logging import get_logger

log = get_logger(__name__)


class ConsoleSmsSender:
    """Development only. Logs the message key, never the code itself."""

    name = "console"

    def send(self, *, phone: PhoneNumber, message_key: str, payload: dict[str, Any]) -> bool:
        log.info(
            "sms.sent",
            phone=phone.masked,
            message_key=message_key,
            # payload deliberately omitted: it carries the OTP.
        )
        return True


class ConsolePushChannel:
    name = "console"

    def send(
        self, *, user_id: str, message_key: str, payload: dict[str, Any], locale: str
    ) -> bool:
        log.info("push.sent", user_id=user_id, message_key=message_key, locale=locale)
        return True


class RecordingNotifier:
    """Writes the notification row, then attempts delivery.

    The row is written first and marked on success, so a notification that
    failed to send is visible in the admin panel rather than lost.
    """

    def __init__(self, notifications, channels: list[Any], clock) -> None:
        self._notifications = notifications
        self._channels = channels
        self._clock = clock

    def notify(
        self,
        *,
        user_id: str,
        message_key: str,
        payload: dict[str, Any],
        locale: str = "fa-AF",
        trip_id: str | None = None,
        booking_id: str | None = None,
    ) -> None:
        from shared.ids import new_id

        for channel in self._channels:
            row = self._notifications.create(
                id=new_id(),
                user_id=user_id,
                message_key=message_key,
                payload=payload,
                channel=channel.name.upper()[:12],
                trip_id=trip_id,
                booking_id=booking_id,
                delivery_status="PENDING",
            )
            try:
                delivered = channel.send(
                    user_id=user_id, message_key=message_key, payload=payload, locale=locale
                )
            except Exception as exc:  # a failing channel must not fail the trip
                row.delivery_status = "FAILED"
                row.failure_reason = type(exc).__name__
                log.warning(
                    "notification.channel_failed",
                    channel=channel.name,
                    message_key=message_key,
                    error=type(exc).__name__,
                )
                continue
            if delivered:
                row.delivery_status = "SENT"
                row.sent_at = self._clock.now()
                return
            row.delivery_status = "FAILED"
