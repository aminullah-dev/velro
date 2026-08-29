"""Time.

House rule: store UTC, tz-aware, ISO-8601. ``datetime.now()`` appears exactly
once in the codebase -- inside ``SystemClock`` -- so that any rule depending on
a boundary date can be tested at that boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """Test double. Advances only when told to."""

    def __init__(self, at: datetime) -> None:
        if at.tzinfo is None:
            raise ValueError("FixedClock requires a timezone-aware datetime")
        self._at = at.astimezone(UTC)

    def now(self) -> datetime:
        return self._at

    def advance(self, seconds: float) -> None:
        self._at = self._at + timedelta(seconds=seconds)


def to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("naive datetime reached the serialisation boundary")
    return value.astimezone(UTC).isoformat()
