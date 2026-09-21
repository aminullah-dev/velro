"""Place names a passenger gives to where they are standing.

A passenger who taps "my current location" is somewhere the map may not know:
only a fraction of Ghorband's villages have ever been placed, and the rest are
names in a spreadsheet with no point. So the app asks what this place is
called, and the answer is kept -- the next passenger standing there is offered
it, and the driver's board says which village the request came from.

That makes every name here public. Once approved it is offered to strangers and
read aloud by drivers, so it must name a *place* -- a village, a town, a bazaar
-- and never a household or a person. "خانه" at a precise coordinate is one
family's front door; "خانهٔ کاکا" is that and a relationship; a phone number is
a person. Those are refused here, before anything is stored, and the reason
travels with the error so the app can say what to write instead.

The rule is deliberately a filter and not a judge. It catches what is certainly
wrong. What it cannot tell -- whether "حاجی گل" is a village or a man -- is left
to staff: a name that does not match a known village waits PENDING until
someone reads it (see PlaceStatus).
"""

from __future__ import annotations

import re

from domain.person_names import clean
from domain.text import comparison_key, normalise
from shared import error_codes
from shared.errors import ValidationError

#: Longer than any real village name, short enough that a sentence is refused.
MAX_LENGTH = 60

#: A place name is a few words. Six is a description ("the house near the
#: mosque by the river"), and a description of where someone lives is exactly
#: what this must not store.
MAX_WORDS = 5

# Words that make a name about one household or one person rather than a
# place. Refused anywhere in the name, alone or not: "خانه", "خانهٔ احمد" and
# "دکان کاکا" all point at somebody's door.
#
# Written in the three languages people here type in. Compared after
# `normalise`, so the Arabic and Persian keyboard forms of each are one entry.
_PERSONAL_WORDS = frozenset(
    normalise(word)
    for word in (
        # home, in Dari, Pashto and English
        "خانه", "خونه", "منزل", "حویلی", "اتاق", "اپارتمان", "آپارتمان",
        "کور", "کورونه", "کوټه", "کوټې",
        "home", "house", "room", "flat", "apartment",
        # work and trade: one person's premises
        "دفتر", "دکان", "دوکان", "مغازه", "کارگاه", "شرکت",
        "office", "shop", "work", "company",
        # family and people
        "پدر", "مادر", "برادر", "خواهر", "کاکا", "ماما", "خاله", "عمه",
        "پسر", "دختر", "زن", "شوهر", "خسر", "خانواده", "فامیل",
        "دوست", "رفیق", "همسایه",
        "پلار", "مور", "ورور", "خور", "تره", "ترور", "زوی", "لور",
        "ښځه", "مېړه", "ملګری", "ګاونډی",
        "mom", "mum", "dad", "father", "mother", "brother", "sister",
        "uncle", "aunt", "family", "friend", "neighbour", "neighbor",
        # my / our
        "من", "مه", "ما", "زما", "زموږ", "مې", "my", "our", "mine",
    )
)

# Suffixes a personal word may carry and still be the same word: the ezafe
# "خانهٔ"/"خانه‌ی", plurals, possessives. Stripped only to recognise a word
# already on the list above, never to match anything new -- "شفاخانه" is a
# hospital, not a home, and stays allowed because "شفا" is not on the list.
_SUFFIXES = ("ی", "ای", "ها", "های", "م", "ت", "ش", "مان", "تان", "شان", "ام", "ات", "اش", "ه")

# Words that name a kind of place rather than a place. Fine beside a real name
# -- "مسجد جامع قلعه نو", "بازار شیخ‌علی" -- and meaningless alone: a passenger
# who writes only "مسجد" has told the next person nothing.
_GENERIC_WORDS = frozenset(
    normalise(word)
    for word in (
        # Not "جاده": it is a road in general and also Jada in Kabul, a real
        # destination -- the master file proved the collision.
        "مسجد", "مکتب", "شفاخانه", "کلینیک", "بازار", "سرک", "کوچه",
        "ایستگاه", "پل", "دریا", "کوه", "دره", "قریه", "ده", "کلی", "شهر",
        "ولسوالی", "مرکز", "اینجا", "همینجا", "اینجه",
        "جومات", "ښوونځی", "روغتون", "ښار", "اډه", "دلته",
        "mosque", "school", "clinic", "bazaar", "market", "road", "street",
        "station", "bridge", "river", "village", "town", "city", "here",
    )
)

_DIGIT = re.compile(r"\d")          # \d matches ۰-۹ and ٠-٩ as well as 0-9
_CONTACT = re.compile(r"@|https?|www\.|\.com|\.af", re.IGNORECASE)


def refusal(value: str | None) -> str | None:
    """Why this is not a place name, or None when it is one.

    Returns a reason rather than a boolean because the app turns each reason
    into its own sentence: "write the village's name, not a house" is useful;
    "invalid" is not.
    """
    # Checked on what was typed, before deciding whether it is a name at all:
    # a bare phone number has no letters, and "that is not a name" would be
    # the wrong thing to tell the person who typed it.
    if value is not None and _DIGIT.search(value):
        # A house number or a phone number. Either way it points at a person.
        return "digits"
    if value is not None and _CONTACT.search(value):
        return "contact"
    name = clean(value)
    if name is None:
        return "empty"
    if len(name) > MAX_LENGTH:
        return "too_long"

    tokens = [t for t in normalise(name).split(" ") if t]
    if not tokens:
        return "empty"
    if len(tokens) > MAX_WORDS:
        return "too_long"
    if any(_is_personal(token) for token in tokens):
        return "personal"
    if all(token in _GENERIC_WORDS for token in tokens):
        return "generic"
    return None


def assert_allowed(value: str | None) -> str:
    """The name to store, or PLACE_NAME_NOT_ALLOWED with its reason."""
    reason = refusal(value)
    if reason is not None:
        raise ValidationError(error_codes.PLACE_NAME_NOT_ALLOWED, reason=reason)
    name = clean(value)
    assert name is not None  # refusal() has already said so
    return name


def place_key(name: str) -> str:
    """The form two reports of one place share.

    The comparison key with its spaces dropped as well: "باغ‌بالا", "باغ بالا"
    and "باغبالا" are one name typed three ways -- ZWNJ, a space, or nothing
    at all -- and must not become three rows in front of staff.
    """
    return comparison_key(name).replace(" ", "")


def _is_personal(token: str) -> bool:
    if token in _PERSONAL_WORDS:
        return True
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and token[: -len(suffix)] in _PERSONAL_WORDS:
            return True
    return False
