"""Localisation completeness.

A key present in English and absent elsewhere fails here rather than shipping:
falling back to English silently is how half-translated products reach users.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from shared.error_codes import REGISTERED_CODES

LOCALES = ("en", "fa-AF", "ps")
RTL_LOCALES = ("fa-AF", "ps")
ROOT = Path(__file__).resolve().parents[2] / "resources" / "locales"

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def load(locale: str) -> dict[str, str]:
    return json.loads((ROOT / f"{locale}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("locale", LOCALES)
def test_every_locale_file_parses(locale: str) -> None:
    assert load(locale), f"{locale} is empty"


@pytest.mark.parametrize("locale", [loc for loc in LOCALES if loc != "en"])
def test_no_key_is_missing_from_a_translation(locale: str) -> None:
    english = set(load("en"))
    translated = set(load(locale))
    assert not (english - translated), f"{locale} is missing: {sorted(english - translated)}"
    assert not (translated - english), f"{locale} has extra: {sorted(translated - english)}"


def test_every_error_code_has_a_message_key() -> None:
    """A code raised with no key to translate would reach a user as a code."""
    english = load("en")
    missing = sorted(
        f"error.{code.lower()}"
        for code in REGISTERED_CODES
        if f"error.{code.lower()}" not in english
    )
    assert not missing, f"error codes without a message: {missing}"


@pytest.mark.parametrize("locale", [loc for loc in LOCALES if loc != "en"])
def test_placeholders_match_the_english_string(locale: str) -> None:
    """A translation that drops {available} renders a sentence with a hole in it."""
    english, translated = load("en"), load(locale)
    mismatched = {
        key: (sorted(set(_PLACEHOLDER.findall(english[key]))),
              sorted(set(_PLACEHOLDER.findall(translated[key]))))
        for key in english
        if set(_PLACEHOLDER.findall(english[key]))
        != set(_PLACEHOLDER.findall(translated.get(key, "")))
    }
    assert not mismatched, f"{locale} placeholder mismatch: {mismatched}"


@pytest.mark.parametrize("locale", LOCALES)
def test_no_translation_is_blank(locale: str) -> None:
    blank = sorted(k for k, v in load(locale).items() if not v.strip())
    assert not blank, f"{locale} has empty strings: {blank}"


@pytest.mark.parametrize("locale", RTL_LOCALES)
def test_rtl_locales_are_written_in_perso_arabic(locale: str) -> None:
    """Catches a key accidentally left as its English source text."""
    latin_only = sorted(
        key
        for key, value in load(locale).items()
        if key not in {"app.name"}
        and not any("؀" <= ch <= "ۿ" for ch in value)
    )
    assert not latin_only, f"{locale} strings still look untranslated: {latin_only}"


def test_pashto_keeps_its_own_letters() -> None:
    """ټ ډ ړ ږ ښ ګ ڼ ې ۍ distinguish real words.

    Their absence across a whole file would mean the text is Persian typed into
    a Pashto file, which is the usual way this ships broken.
    """
    text = " ".join(load("ps").values())
    pashto_letters = set("ټډړږښګڼېۍ")
    present = {ch for ch in pashto_letters if ch in text}
    assert len(present) >= 6, f"Pashto file uses too few Pashto-specific letters: {present}"
