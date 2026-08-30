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
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    # The registered alphanumeric sender ID -- what Etisalat, MTN, Roshan and
    # Salaam require, and what AWCC refuses. Registration takes about a week.
    twilio_sender_id: str = ""
    # A number, for AWCC and for anywhere the sender ID is refused. Twilio sells
    # no Afghan long code, so this is an international one.
    twilio_sender_number: str = ""
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
    "twilio_account_sid": "",
    "twilio_auth_token": "",
    "twilio_sender_id": "",
    "twilio_sender_number": "",
    "push_provider": "console",
    "storage_root": "var/storage",
    # Both tuple-typed, and both absent from this dict until now. `_coerce`
    # only knows to split a comma-separated env value when the *existing*
    # value it is replacing is already a tuple -- so with no entry here,
    # setting VELRO_CORS_ORIGINS or VELRO_SUPPORTED_LOCALES silently produced
    # a bare string instead. cors_origins then reached
    # `CORSMiddleware(allow_origins=list(cfg.cors_origins))` in ui/api/app.py,
    # and list() on a string explodes it into individual characters -- found
    # only by setting the variable for the first time, for this deployment.
    "cors_origins": (),
    "supported_locales": ("en", "fa-AF", "ps"),
}

_REQUIRED = ("database_url", "jwt_secret")
_ENV_PREFIX = "VELRO_"
# Ours, but not application settings, so `load` never reads them and the stray
# check below would otherwise reject them. Listed one by one rather than by
# pattern: the whole value of that check is that an unrecognised VELRO_ variable
# stops the server, and a wildcard is how it stops recognising anything.
_ENV_EXCEPTIONS = frozenset(
    {
        "VELRO_CONFIG",           # which file to read, read before the file
        "VELRO_TEST_DATABASE_URL",  # the test harness picks its own database
    }
)


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

    # A VELRO_-prefixed variable matching no setting is a typo, and a typo is a
    # setting somebody believes they made. It stayed at its default in silence:
    # VELRO_SMS_PROVIDR=twilio leaves a production server on the console sender
    # that delivers nothing. Named exceptions rather than a prefix free-for-all,
    # because the environment legitimately carries a few of our own.
    settable = {
        f"{_ENV_PREFIX}{key.upper()}"
        for key in {*values, *_REQUIRED, "supported_locales", "cors_origins"}
    }
    strays = sorted(
        name
        for name in env
        if name.startswith(_ENV_PREFIX)
        and name not in settable
        and name not in _ENV_EXCEPTIONS
    )
    if strays:
        raise ConfigurationError(
            "unknown environment variables (a typo leaves the setting at its "
            "default): " + ", ".join(strays)
        )

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

    # The one setting that must not merely default to off.
    #
    # otp_debug_echo returns the OTP in the API response, so a deployment with
    # it on hands the code for any phone number to anyone who asks for it. That
    # is not a debug leak, it is every account in Ghorband: the person does not
    # need the handset, the network, or the server -- only the number.
    #
    # Defaulting to False protects a deployment nobody misconfigures. This
    # refuses to start one that somebody did, because the failure is silent and
    # total, and an environment variable set once during a demo outlives the
    # demo.
    if settings.is_production and settings.otp_debug_echo:
        raise ConfigurationError(
            f"{_ENV_PREFIX}OTP_DEBUG_ECHO cannot be on in production: it returns "
            "the sign-in code to whoever asks for it"
        )
    if settings.is_production and settings.sms_provider == "console":
        # The console sender delivers nothing. In production that is an
        # authentication system that cannot sign anybody in, discovered by the
        # first real person who tries.
        raise ConfigurationError(
            f"{_ENV_PREFIX}SMS_PROVIDER is 'console' in production: no message "
            "would ever reach a handset"
        )
    return settings
