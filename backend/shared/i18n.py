"""Turning a message key into words, on the server.

Almost nothing here needs this. Every other channel hands a client a key and a
payload and lets the device render, which is what keeps one person's language
from depending on what some server thought at the time.

SMS cannot do that. It carries finished text, so somebody has to choose the
words, and the only somebody available is us.

The same three files the apps use. Not a copy: `resources/locales/*.json` is
what the mobile build copies at build time and what the admin syncs, so a
sentence cannot say one thing on a handset and another in a text message.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

_LOCALES = Path(__file__).resolve().parent.parent / "resources" / "locales"
_PLACEHOLDER = re.compile(r"\{(\w+)\}")

DEFAULT_LOCALE = "fa-AF"


class MessageKeyUnknownError(KeyError):
    """Raised rather than falling back to the key itself.

    A key that reaches a handset as `auth.sms.otp` is a text message that says
    nothing to the person reading it, and it costs the same as one that does.
    Better to fail where a test can see it.
    """


@cache
def _messages(locale: str) -> dict[str, str]:
    path = _LOCALES / f"{locale}.json"
    if not path.is_file():
        raise MessageKeyUnknownError(f"no messages for locale {locale!r}")
    return json.loads(path.read_text(encoding="utf-8"))


def render(message_key: str, *, locale: str, **payload: object) -> str:
    """The sentence, in the language asked for.

    Falls back to the default locale only when the locale itself is unknown --
    never per key. Key parity across the three files is enforced by a test, so
    a per-key fallback would hide a missing translation until it was somebody's
    sign-in message.
    """
    try:
        messages = _messages(locale)
    except MessageKeyUnknownError:
        messages = _messages(DEFAULT_LOCALE)

    template = messages.get(message_key)
    if template is None:
        raise MessageKeyUnknownError(message_key)

    missing = {
        name for name in _PLACEHOLDER.findall(template) if name not in payload
    }
    if missing:
        # A hole in a sentence somebody is about to be charged for.
        raise MessageKeyUnknownError(
            f"{message_key} needs {sorted(missing)}, which was not supplied"
        )

    return _PLACEHOLDER.sub(lambda m: str(payload[m.group(1)]), template)
