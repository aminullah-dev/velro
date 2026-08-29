"""Structured logging.

One line per event, JSON in production. Never log passwords, full tokens, OTP
codes, identity-document contents or complete request bodies -- redaction is
installed at the handler, not left to call sites.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_REDACTED = "[redacted]"
_SENSITIVE_KEYS = frozenset(
    {
        "password", "passwd", "secret", "token", "access_token", "refresh_token",
        "authorization", "code", "code_hash", "otp", "otp_code", "verification_code",
        "national_id", "license_number", "qr_payload", "private_key", "api_key",
    }
)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: (_REDACTED if k.lower() in _SENSITIVE_KEYS else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


class TextFormatter(logging.Formatter):
    """Human-readable, for development. Renders the structured context too --
    a log line that drops its context is not worth writing."""

    def format(self, record: logging.LogRecord) -> str:
        base = f"{self.formatTime(record)} {record.levelname:<8} {record.getMessage()}"
        context = getattr(record, "context", None)
        if isinstance(context, dict) and context:
            rendered = " ".join(
                f"{k}={v}" for k, v in sorted(redact(context).items()) if k != "traceback"
            )
            base = f"{base} {rendered}"
            if "traceback" in context:
                base = f"{base}\n{context['traceback']}"
        return base


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "event": record.getMessage(),
            "logger": record.name,
        }
        extra = getattr(record, "context", None)
        if isinstance(extra, dict):
            payload.update(redact(extra))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class EventLogger:
    """Thin wrapper so call sites read as ``log.info("payment.recorded", ...)``."""

    def __init__(self, name: str) -> None:
        self._log = logging.getLogger(name)

    def _emit(self, level: int, event: str, **context: Any) -> None:
        self._log.log(level, event, extra={"context": context})

    def debug(self, event: str, **c: Any) -> None:
        self._emit(logging.DEBUG, event, **c)

    def info(self, event: str, **c: Any) -> None:
        self._emit(logging.INFO, event, **c)

    def warning(self, event: str, **c: Any) -> None:
        self._emit(logging.WARNING, event, **c)

    def error(self, event: str, **c: Any) -> None:
        self._emit(logging.ERROR, event, **c)

    def critical(self, event: str, **c: Any) -> None:
        self._emit(logging.CRITICAL, event, **c)


def configure(level: str = "INFO", json_output: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if json_output else TextFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def get_logger(name: str) -> EventLogger:
    return EventLogger(name)
