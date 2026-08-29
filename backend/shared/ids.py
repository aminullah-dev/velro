"""UUIDv7 identifiers.

House rule (platform-core/conventions): UUIDv7, string, 36 chars, generated in
the application layer and never by the database. Time-ordered so a B-tree index
does not fragment the way UUIDv4 does; string rather than a native UUID type so
SQLite and PostgreSQL behave identically.
"""

from __future__ import annotations

import os
import time
from typing import Protocol

_UNIX_TS_MS_BITS = 48
_RAND_A_BITS = 12


def new_id() -> str:
    """Return a fresh UUIDv7 as a 36-character lowercase string."""
    return _uuid7(time.time_ns() // 1_000_000)


def _uuid7(unix_ts_ms: int) -> str:
    if unix_ts_ms < 0 or unix_ts_ms >= (1 << _UNIX_TS_MS_BITS):
        raise ValueError("timestamp out of range for UUIDv7")

    rand = int.from_bytes(os.urandom(10), "big")
    rand_a = (rand >> 62) & ((1 << _RAND_A_BITS) - 1)
    rand_b = rand & ((1 << 62) - 1)

    value = unix_ts_ms << 80          # 48 bits of millisecond timestamp
    value |= 0x7 << 76                # version 7
    value |= rand_a << 64             # 12 bits of randomness
    value |= 0b10 << 62               # RFC 4122 variant
    value |= rand_b                   # 62 bits of randomness

    hexed = f"{value:032x}"
    return f"{hexed[0:8]}-{hexed[8:12]}-{hexed[12:16]}-{hexed[16:20]}-{hexed[20:32]}"


def timestamp_ms_of(uuid7: str) -> int:
    """Extract the embedded millisecond timestamp. Used only by tests and tooling."""
    return int(uuid7.replace("-", "")[:12], 16)


class IdGenerator(Protocol):
    """Injected wherever an id is needed, so use cases stay deterministic in tests."""

    def __call__(self) -> str: ...
