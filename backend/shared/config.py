"""Configuration.

Three sources in ascending precedence: bundled defaults -> config file next to
the executable -> environment variables. Secrets never live in the config file
that ships. A missing required setting fails at startup with a named error, not
at first use.

Note the distinction from ``app_settings`` in the database: this file holds
*deployment* configuration (where the database is, which secret signs a token).
Anything an operator should be able to change without a redeploy -- commission
rate, cancellation policy, OTP lifetime, emergency numbers -- is a row in
``app_settings``, never a constant here. See section 104/105 of the product
specification.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigurationError(Exception):
    """A required setting is absent or malformed. Raised at startup only."""


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    database_url: str
    jwt_secret: str
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 60 * 60 * 24 * 30
    default_locale: str = "fa-AF"
    supported_locales: tuple[str, ...] = ("en", "fa-AF", "ps")
    default_currency: str = "AFN"
    default_timezone: str = "Asia/Kabul"
    log_level: str = "INFO"
    log_json: bool = True
    idempotency_ttl_seconds: int = 60 * 60 * 24
    otp_debug_echo: bool = False
    sms_provider: str = "console"
    push_provider: str = "console"
    storage_root: str = "var/storage"
    cors_origins: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


_DEFAULTS: dict[str, Any] = {
    "environment": "development",
    "jwt_access_ttl_seconds": 900,
    "jwt_refresh_ttl_seconds": 60 * 60 * 24 * 30,
    "default_locale": "fa-AF",
    "default_currency": "AFN",
    "default_timezone": "Asia/Kabul",
    "log_level": "INFO",
    "log_json": True,
    "idempotency_ttl_seconds": 60 * 60 * 24,
    "otp_debug_echo": False,
    "sms_provider": "console",
    "push_provider": "console",
    "storage_root": "var/storage",
}

_REQUIRED = ("database_url", "jwt_secret")
_ENV_PREFIX = "VELRO_"


def _coerce(target: Any, raw: str) -> Any:
    if isinstance(target, bool):
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(target, int):
        return int(raw)
    if isinstance(target, tuple):
        return tuple(part.strip() for part in raw.split(",") if part.strip())
    return raw


def load(config_path: str | Path | None = None, env: dict[str, str] | None = None) -> Settings:
    env = dict(os.environ if env is None else env)
    values: dict[str, Any] = dict(_DEFAULTS)

    path = Path(config_path) if config_path else Path(env.get(f"{_ENV_PREFIX}CONFIG", "velro.toml"))
    if path.is_file():
        with path.open("rb") as handle:
            values.update(tomllib.load(handle))

    for key in {*values, *_REQUIRED, "supported_locales", "cors_origins"}:
        raw = env.get(f"{_ENV_PREFIX}{key.upper()}")
        if raw is not None:
            values[key] = _coerce(values.get(key), raw)

    missing = [key for key in _REQUIRED if not values.get(key)]
    if missing:
        raise ConfigurationError(
            "missing required configuration: "
            + ", ".join(f"{_ENV_PREFIX}{k.upper()}" for k in sorted(missing))
        )

    known = {f.name for f in Settings.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    unknown = sorted(set(values) - known)
    if unknown:
        raise ConfigurationError(f"unknown configuration keys: {', '.join(unknown)}")

    for key in ("supported_locales", "cors_origins"):
        if key in values and isinstance(values[key], list):
            values[key] = tuple(values[key])

    settings = Settings(**values)
    if settings.default_locale not in settings.supported_locales:
        raise ConfigurationError(
            f"default_locale {settings.default_locale!r} is not in supported_locales"
        )
    return settings
