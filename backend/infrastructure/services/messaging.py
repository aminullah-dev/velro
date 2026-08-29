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


class DeviceTokenPushChannel:
    """Push to a person's registered devices.

    Delivery is attempted through whichever transport is configured. With none
    configured -- which is the case until Firebase credentials exist -- this
    still writes the notification row and reports not-delivered, so the message
    is waiting in the app when the person next opens it and the failure is
    visible in the admin panel rather than silent.

    A push is a convenience. The inbox is the record.
    """

    name = "push"

    def __init__(self, tokens, transport=None, *, app: str | None = None) -> None:
        self._tokens = tokens
        self._transport = transport
        self._app = app

    def send(
        self, *, user_id: str, message_key: str, payload: dict[str, Any], locale: str
    ) -> bool:
        rows = self._tokens.for_users([user_id], app=self._app)
        if not rows:
            log.info("push.no_device", user_id=user_id, message_key=message_key)
            return False
        if self._transport is None:
            log.info(
                "push.not_configured",
                user_id=user_id, message_key=message_key, devices=len(rows),
            )
            return False

        delivered = False
        for row in rows:
            try:
                ok = self._transport.send(
                    token=row.token, message_key=message_key,
                    payload=payload, locale=row.locale or locale,
                )
            except TokenRejectedError:
                # The device is gone -- uninstalled, or the token rotated.
                # Keeping it means retrying a dead address for ever.
                self._tokens.forget(row.token)
                continue
            delivered = delivered or bool(ok)
        return delivered


class TokenRejectedError(Exception):
    """The push service says this token no longer addresses anything."""


def build_notifier(notifications, tokens, clock, *, transport=None, app=None):
    """The notifier the API uses.

    One place that decides which channels exist, so wiring Firebase later is a
    transport passed in here rather than an edit at every call site.
    """
    return RecordingNotifier(
        notifications,
        [DeviceTokenPushChannel(tokens, transport, app=app)],
        clock,
    )
