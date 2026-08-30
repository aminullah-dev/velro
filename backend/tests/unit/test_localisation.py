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
    """Catches a key accidentally left as its English source text.

    A string with no Latin letters at all is exempt: "{label} × {count}" is
    entirely placeholders and punctuation, so there is no English left in it to
    catch. Requiring a Perso-Arabic character there would force a word into a
    string that reads correctly without one.
    """
    latin_only = sorted(
        key
        for key, value in load(locale).items()
        if key not in {"app.name"}
        and any("a" <= ch.lower() <= "z" for ch in _outside_placeholders(value))
        and not any("؀" <= ch <= "ۿ" for ch in value)
    )
    assert not latin_only, f"{locale} strings still look untranslated: {latin_only}"


def _outside_placeholders(value: str) -> str:
    """The text a reader actually sees, with ``{name}`` removed.

    A placeholder name is always Latin -- it is a variable, not prose -- so
    leaving them in would make every parameterised string look untranslated.
    """
    return re.sub(r"\{[^}]*\}", "", value)


def test_pashto_keeps_its_own_letters() -> None:
    """ټ ډ ړ ږ ښ ګ ڼ ې ۍ distinguish real words.

    Their absence across a whole file would mean the text is Persian typed into
    a Pashto file, which is the usual way this ships broken.
    """
    text = " ".join(load("ps").values())
    pashto_letters = set("ټډړږښګڼېۍ")
    present = {ch for ch in pashto_letters if ch in text}
    assert len(present) >= 6, f"Pashto file uses too few Pashto-specific letters: {present}"


# -- keys the surfaces actually ask for -----------------------------------

_REPO = Path(__file__).resolve().parents[3]


def _literal_keys(root: Path, patterns: tuple[str, ...]) -> dict[str, set[Path]]:
    """Every message key written as a literal in source.

    Interpolated lookups -- ``t(`document.type.${code}`)`` -- cannot be read
    statically and are not covered here; those families are checked by the
    tests that exercise the endpoint returning the code.
    """
    found: dict[str, set[Path]] = {}
    if not root.is_dir():
        return found
    for path in root.rglob("*"):
        if path.suffix not in {".ts", ".tsx", ".kt"} or not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                found.setdefault(match.group(1), set()).add(path)
    return found


def test_every_key_the_admin_panel_asks_for_exists() -> None:
    """A missing key does not crash -- it renders as ``ADMIN.COL.AMOUNT`` on
    screen, which is how this was found. The test is cheaper than the review."""
    english = load("en")
    # The lookbehind matters: without it the pattern also matches the tail of
    # any identifier ending in t -- part("year"), format("x") -- and reports
    # their arguments as missing message keys.
    used = _literal_keys(
        _REPO / "admin" / "src",
        (r'(?<![A-Za-z0-9_$.])t\("([a-z][a-zA-Z0-9._]*)"\)',),
    )
    missing = {k: v for k, v in used.items() if k not in english}
    assert not missing, "admin keys with no message: " + ", ".join(sorted(missing))


def test_every_key_the_apps_ask_for_exists() -> None:
    english = load("en")
    used = _literal_keys(
        _REPO / "mobile",
        (
            r'strings\["([a-z][a-zA-Z0-9._]*)"',
            r'strings\.get\("([a-z][a-zA-Z0-9._]*)"',
        ),
    )
    missing = {k: v for k, v in used.items() if k not in english}
    assert not missing, "app keys with no message: " + ", ".join(sorted(missing))


def test_every_fare_component_key_has_a_message() -> None:
    """The receipt renders these by key, interpolated -- so the source scan
    above cannot see them. They are checked against the pricing code that
    emits them instead, which is the only place they are decided."""
    english = load("en")
    emitted = set()
    for path in (_REPO / "backend" / "application" / "pricing").rglob("*.py"):
        emitted |= set(re.findall(r'"(fare\.component\.[a-z_]+)"', path.read_text()))

    assert emitted, "no fare component keys found -- has the pricing engine moved?"
    missing = sorted(k for k in emitted if k not in english)
    assert not missing, f"fare components with no message: {missing}"


def test_every_notification_message_key_has_a_message() -> None:
    """These are chosen in the use cases and rendered on a device.

    Nothing in the source scan sees them -- the app looks them up by whatever
    the server sent -- so they are checked against the code that emits them.
    """
    english = load("en")
    emitted = set()
    for path in (_REPO / "backend" / "application").rglob("*.py"):
        emitted |= set(
            re.findall(r'message_key="(notify\.[a-z_.]+)"', path.read_text())
        )

    assert emitted, "no notification keys found -- have the use cases moved?"
    missing = sorted(k for k in emitted if k not in english)
    assert not missing, f"notifications with no message: {missing}"


def test_the_apps_built_in_safety_categories_match_the_domain() -> None:
    """The emergency sheet ships a compiled-in copy of the ticket categories.

    It has to: the numbers and the form must work on a handset that has never
    reached the server. The cost of that is a second copy of the list, and this
    is what stops it drifting -- a category the app offers and the domain
    rejects is a report form that fails on submit, for somebody who has just
    described being in danger.
    """
    from domain.support import CATEGORIES, URGENT_CATEGORIES

    source = (
        _REPO / "mobile" / "domain" / "src" / "main" / "kotlin" / "af" / "velro"
        / "domain" / "Entities.kt"
    ).read_text(encoding="utf-8")

    block = re.search(r"val BUILT_IN = SafetyContacts\((.*?)\n        \)", source, re.S)
    assert block, "SafetyContacts.BUILT_IN not found in the Kotlin domain"

    def ordered(field: str) -> list[str]:
        section = re.search(rf"{field} = listOf\((.*?)\)", block.group(1), re.S)
        assert section, f"{field} not found in SafetyContacts.BUILT_IN"
        return re.findall(r'"([A-Z_]+)"', section.group(1))

    def listed(field: str) -> set[str]:
        return set(ordered(field))

    assert listed("categories") == CATEGORIES
    assert listed("urgentCategories") == URGENT_CATEGORIES

    # And in the same order, because the order is the triage. A handset with no
    # connection renders this list, so SAFETY being seventh here is the same
    # defect as SAFETY being seventh on the server -- just harder to notice.
    from ui.api.routers.support import _ordered

    assert ordered("categories") == _ordered(CATEGORIES)


def test_every_safety_string_the_sheet_asks_for_exists() -> None:
    """A missing key renders as `safety.not_rescue` on the emergency screen."""
    english = load("en")
    source_root = _REPO / "mobile" / "feature" / "safety"
    used = _literal_keys(source_root, (r'strings\["([a-z][a-zA-Z0-9._]*)"',))
    missing = {k for k in used if k not in english}
    assert not missing, f"the help sheet asks for keys with no message: {sorted(missing)}"


def test_the_safety_promise_matches_what_the_message_carries() -> None:
    """The hint must not promise a field the body does not have.

    It said "the car, the driver and where you are" while safety.sms_body
    carried plate, driver, booking and journey and no location at all -- and
    the design deliberately refuses location, because a movement trail on a
    woman is something VELRO would then hold and could be compelled to hand
    over. A promise of a coordinate that is not in the message is the exact
    failure this whole feature exists to prevent, and it was in the copy.
    """
    for locale in LOCALES:
        messages = load(locale)
        body = messages["safety.sms_body"]
        hint = messages["safety.tell_someone_hint"]

        assert "{maps_url}" not in body, (
            f"{locale}: the message claims a location the app never supplies"
        )
        # Every placeholder the body promises must be one the app fills in.
        supplied = {"plate", "driver", "driver_phone", "booking", "origin", "destination"}
        used = set(re.findall(r"\{(\w+)\}", body))
        assert used <= supplied, f"{locale}: sms_body uses {used - supplied}"

        # And the hint must not mention a location either, in any script.
        for word in ("location", "موقعیت", "ځای", "where you are"):
            assert word not in hint, (
                f"{locale}: the hint promises {word!r}, which the message "
                "does not carry"
            )


def test_no_person_is_rendered_as_a_dash() -> None:
    """A missing person is a fact, and an em-dash does not state it.

    The rule is deliberately narrow. A dash for a distance nobody measured or a
    destination with no parent is honest -- there is no sentence to say. A dash
    where a *person* belongs is different: it is the answer to "who drove me",
    "who do I collect this money from", "who suspended this driver". Those have
    answers, and where the name is absent the phone or the id is the answer.

    Scoped to fields whose name says they hold a person, so it cannot be
    satisfied by deleting the dash from a distance column.
    """
    offenders: list[str] = []
    # Named one by one on purpose. A pattern over anything ending in "name"
    # also catches parent_name and origin_station_name, which are places: a
    # place nobody named has no phone number and no id, so the dash there is
    # the whole truth. These eight are people.
    people = (
        "driver_name", "driverName",
        "passenger_name", "passengerName",
        "full_name", "fullName",
        "actor_name", "actorName",
    )
    pattern = re.compile(r'(?:{})\s*\?[?:]\s*"—"'.format("|".join(people)))
    roots = (
        (_REPO / "mobile", (".kt",)),
        (_REPO / "admin" / "src", (".tsx", ".ts")),
    )
    for root, suffixes in roots:
        for path in root.rglob("*"):
            if path.suffix not in suffixes or "/build/" in str(path):
                continue
            for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if pattern.search(line):
                    offenders.append(f"{path.relative_to(_REPO)}:{number}")
    assert not offenders, "a person rendered as a dash: " + ", ".join(sorted(offenders))


# A GSM-7 message is 160 characters; anything outside that alphabet forces the
# whole message into UCS-2, which is 70. Dari and Pashto are always UCS-2.
_GSM7 = set(
    "@£$¥èéùìòÇØøÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà\n\r"
)


@pytest.mark.parametrize("locale", LOCALES)
def test_the_sign_in_message_fits_one_sms(locale: str) -> None:
    """Going one character over doubles the price of every sign-in.

    A network charges per segment, not per message, and Perso-Arabic forces
    UCS-2 -- so Dari and Pashto get 70 characters, not 160. The Pashto text is
    currently 54. There is room, and there is not much room, and the person who
    spends it will be editing a translation and thinking about wording.

    At the rates quoted for Afghan operators a second segment is roughly a
    third of a dollar per sign-in, which is the largest single running cost
    VELRO has.
    """
    rendered = (
        load(locale)["auth.sms.otp"]
        # The longest realistic substitution: a 6-digit code and a 2-digit TTL.
        .replace("{code}", "123456")
        .replace("{ttl_minutes}", "10")
    )
    limit = 160 if all(character in _GSM7 for character in rendered) else 70
    assert len(rendered) <= limit, (
        f"{locale}: the sign-in SMS is {len(rendered)} characters and the limit "
        f"is {limit}. A second segment doubles the cost of every sign-in."
    )
