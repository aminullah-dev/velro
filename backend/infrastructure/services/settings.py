"""Operator-tunable settings.

Section 105: no district, price, commission, route, vehicle type or status is
hard-coded. These are rows, read through this provider, cached for the lifetime
of a request only -- an operator changing the commission rate must not have to
wait for a deploy or a restart.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from infrastructure.db.models.ops import SettingRow
from shared import error_codes
from shared.errors import InfrastructureError

# Defaults exist so a fresh database is usable, and so a missing row is a
# recoverable condition rather than a crash. Seeding writes these as real rows.
DEFAULTS: dict[str, Any] = {
    "commission.rate_basis_points": 1000,             # 10%
    "booking.max_active_per_passenger": 5,
    "booking.max_seats_per_booking": 4,
    "booking.cancellation_window_minutes": 15,
    # How long before departure a trip stops taking bookings. Zero is the
    # departure time itself, and the floor: whatever this says, a seat is
    # never sold on a vehicle whose scheduled departure has passed.
    "booking.cutoff_minutes": 0,
    "booking.verification_code_length": 4,
    "otp.length": 5,
    "otp.ttl_seconds": 300,
    "otp.max_attempts": 5,
    "otp.resend_window_seconds": 60,
    "otp.max_per_window": 3,
    # 30 seconds is the figure a hailing product would use, where the driver
    # gets a push and the phone is in a cradle. Here the app polls over an
    # intermittent connection, so a short window means offers expire before a
    # driver ever sees them.
    "dispatch.offer_ttl_seconds": 180,
    # How far from the nearest station a caller may stand and still summon
    # drivers. Generous, because a village sits off the road its station is
    # on; zero turns the fence off entirely. ui/api/geofence.py is the reader.
    "geofence.radius_m": 20_000,
    "dispatch.max_offers_per_trip": 10,
    # A trip leaving within this many minutes with nobody to drive it is the
    # board's red row and the dashboard's "departures at risk".
    "dispatch.at_risk_minutes": 60,
    # A driver who is online but whose last position is older than this is
    # counted as "no fix": dispatch ranks him last, and the dashboard says
    # so, because a car the office cannot place is a car it cannot send.
    # The handset pings every location_ping_seconds; fifteen missed pings.
    "dispatch.stale_gps_seconds": 300,
    # A passenger's request with no offer after this long is one the office
    # should be ringing drivers about.
    "dispatch.unanswered_after_minutes": 10,
    # SELFIE sits beside NATIONAL_ID deliberately. A tazkira proves a document
    # exists; it does not prove the person holding the account is the person on
    # it. A passenger getting into a stranger's car in a valley at night is
    # trusting that VELRO checked exactly that, and a borrowed or stolen tazkira
    # defeats it entirely.
    "driver.required_documents": [
        "LICENSE", "NATIONAL_ID", "SELFIE",
    ],
    # جواز سیر is the car's permit, not the driver's. A driver who owns two
    # vehicles holds two of them, and the first cannot certify the second --
    # which is exactly what happened while this sat in the list above.
    "vehicle.required_documents": ["VEHICLE_REGISTRATION"],
    "vehicle.optional_documents": [],
    "driver.location_ping_seconds": 20,
    # Which country a phone number typed without a prefix belongs to.
    # Ghorband is +93. A row, not a constant, so a test deployment can
    # point at a real handset somewhere else without editing code.
    "auth.default_country_code": "93",
    "support.emergency_numbers": ["119", "100"],
    "support.contact_phone": "+93700000000",
    "trip.search_window_hours": 12,
    # A payout costs someone a journey. Below this the errand is worth more
    # than the money, so drivers are asked to let it accumulate.
    "settlement.minimum_minor": 50_000,           # 500 AFN
}


class SqlSettingsProvider:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._cache: dict[str, Any] | None = None

    def _all(self) -> dict[str, Any]:
        if self._cache is None:
            rows = self._session.scalars(
                select(SettingRow).where(SettingRow.deleted_at.is_(None))
            ).all()
            self._cache = {row.key: _unwrap(row.value) for row in rows}
        return self._cache

    def _get(self, key: str, default: Any) -> Any:
        value = self._all().get(key, DEFAULTS.get(key, default))
        if value is None:
            raise InfrastructureError(error_codes.SETTING_NOT_FOUND, key=key)
        return value

    def get_int(self, key: str, default: int | None = None) -> int:
        value = self._get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise InfrastructureError(
                error_codes.SETTING_TYPE_INVALID, key=key, expected="int", got=type(value).__name__
            )
        return value

    def get_str(self, key: str, default: str | None = None) -> str:
        value = self._get(key, default)
        if not isinstance(value, str):
            raise InfrastructureError(
                error_codes.SETTING_TYPE_INVALID, key=key, expected="str", got=type(value).__name__
            )
        return value

    def get_bool(self, key: str, default: bool | None = None) -> bool:
        value = self._get(key, default)
        if not isinstance(value, bool):
            raise InfrastructureError(
                error_codes.SETTING_TYPE_INVALID, key=key, expected="bool", got=type(value).__name__
            )
        return value

    def get_list(self, key: str, default: list[str] | None = None) -> list[str]:
        value = self._get(key, default)
        if not isinstance(value, list):
            raise InfrastructureError(
                error_codes.SETTING_TYPE_INVALID, key=key, expected="list", got=type(value).__name__
            )
        return list(value)

    def invalidate(self) -> None:
        self._cache = None


def _unwrap(stored: Any) -> Any:
    """Values are stored as JSON so a list or an object round-trips intact.

    Everything written through `wrap` arrives as ``{"v": ...}``. A bare value
    means the row was written by hand -- a migration, or somebody at a psql
    prompt -- and the driver has already decoded it.

    A scalar string is therefore returned as a string, never re-parsed. The
    previous version ran json.loads on it, so a setting whose value happened to
    look like a number changed type on the way out: "93" became 93 and every
    get_str for it raised SETTING_TYPE_INVALID -- for every user at once, from
    a row that reads correctly in the database. Only text that is plainly a
    JSON container is parsed, because that is the one case where keeping it as
    a string would be the surprise.
    """
    if isinstance(stored, dict) and set(stored) == {"v"}:
        return stored["v"]
    if isinstance(stored, str):
        head = stored.lstrip()[:1]
        if head in ("{", "["):
            try:
                return json.loads(stored)
            except json.JSONDecodeError:
                return stored
    return stored


def wrap(value: Any) -> dict[str, Any]:
    """Scalars need an object wrapper because the column is JSON, not JSONB-any."""
    return {"v": value}
