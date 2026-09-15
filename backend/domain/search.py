"""What an operator types into a search box, read the way he meant it.

The staff console's search boxes are typed on whatever keyboard the operator
has open, and on a Persian or Pashto layout the digits come out as ۰۷۰۰ rather
than 0700. The number itself arrives from a driver's complaint as 0700 123 456
while the row holds +93700123456. None of that is the operator's problem: he
typed the right number, and the search should find it.

Only the comparison is normalised. Nothing here is stored or displayed -- the
same rule as village names and number plates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from domain.driver import normalise_plate
from domain.text import normalise_digits

#: Digits and the punctuation people put between them, nothing else. A term
#: with a letter in it is a name or a plate, and reading its digits as a phone
#: would match every driver whose number happens to contain them.
_PHONE_SHAPED = re.compile(r"[+\d\s\-().]+")

#: Fewer significant digits than this match half the fleet and answer nothing.
MIN_PHONE_DIGITS = 3


@dataclass(frozen=True, slots=True)
class SearchTerm:
    #: What was typed, trimmed, inner whitespace collapsed, digits in Latin.
    text: str
    #: The significant digits of a phone-shaped term, or None. Leading zeros
    #: are dropped, which is what makes one contains-match serve every form:
    #: 0700123456 -> 700123456, 0093700123456 -> 93700123456, and both are
    #: inside +93700123456.
    phone_digits: str | None
    #: The term in number-plate comparison form (see normalise_plate), or None
    #: when nothing alphanumeric is left.
    plate_key: str | None

    @classmethod
    def parse(cls, raw: str | None) -> SearchTerm | None:
        """None for an absent or blank box: no filter, not "match nothing"."""
        if raw is None:
            return None
        text = " ".join(normalise_digits(raw).split())
        if not text:
            return None

        phone = None
        if _PHONE_SHAPED.fullmatch(text):
            significant = "".join(ch for ch in text if ch.isdigit()).lstrip("0")
            if len(significant) >= MIN_PHONE_DIGITS:
                phone = significant

        return cls(text=text, phone_digits=phone, plate_key=normalise_plate(text) or None)

    @property
    def like_pattern(self) -> str:
        """A contains-pattern for ``ILIKE ... ESCAPE '\\'``.

        The operator's % and _ are characters he typed, not wildcards: a search
        for "%" must not return every row.
        """
        escaped = (
            self.text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        return f"%{escaped}%"


def normalise_business_number(raw: str) -> str:
    """VLR-2026-000047 however it was typed: trimmed, upper case, Latin digits.

    Exact otherwise. A business number is an identifier, and a lookup that
    guessed at a mistyped one would open the wrong trip.
    """
    return normalise_digits(raw).strip().upper()
