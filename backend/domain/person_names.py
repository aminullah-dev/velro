"""What a person typed, minus what cannot be seen.

Deliberately not `domain.text`. That module folds ی/ي, ک/ك and the alef forms
and deletes the zero-width non-joiner, which is right for proposing that two
spreadsheet rows are the same village and wrong for a person: it would store
نجیبالله for a man who typed نجیب‌الله, and flatten بی‌بی. It says so itself --
"normalising for storage would quietly rewrite people's place names". A name is
even less ours to rewrite than a village's.

So no letter here is ever changed. The only things removed are things that
cannot be seen: control characters, byte-order marks, bidi overrides, and runs
of whitespace.

The one judgement this makes is whether the text is a name at all.
"""

from __future__ import annotations

import re
import unicodedata

# Invisible: C0/C1 controls, the byte-order mark, and the bidi formatting
# characters. A name is read aloud down a phone line and printed on a receipt;
# an embedded right-to-left override in it is either an accident or an attack,
# and in neither case is it part of what the person is called.
#
# Built from code points rather than written as literals, because literals here
# are invisible by definition: a reviewer cannot see what is inside the
# brackets, and neither can a diff.
#
# U+200C, the zero-width non-joiner, is deliberately absent. It is not noise in
# Perso-Arabic -- it is the difference between نجیب‌الله and نجیبالله.
_INVISIBLE_RANGES = (
    (0x0000, 0x0008), (0x000B, 0x000C), (0x000E, 0x001F),  # C0 controls
    (0x007F, 0x009F),                                      # DEL and C1
    (0xFEFF, 0xFEFF),                                      # byte-order mark
    (0x200E, 0x200F),                                      # LRM, RLM
    (0x202A, 0x202E),                                      # embedding, override
    (0x2066, 0x2069),                                      # isolates
)
_INVISIBLE = re.compile(
    "[" + "".join(f"{chr(lo)}-{chr(hi)}" for lo, hi in _INVISIBLE_RANGES) + "]"
)

_WHITESPACE = re.compile(r"\s+")

# Two letters. Not a length: گل is a real name and "..." is not, and counting
# characters cannot tell them apart.
_MINIMUM_LETTERS = 2


def clean(value: str | None) -> str | None:
    """The name to store, or None when what was typed is not a name.

    Returning None rather than raising is the whole design. The field is
    optional everywhere it appears, and the person filling it is often standing
    at a station, one-thumbed, with a keyboard covering half the screen and the
    button he actually wants hidden behind the form. Some of them will type a
    single letter to get past it.

    An error would make that person's problem worse. Silently storing "G" would
    be worse still: every place a missing name falls back to something usable --
    the driver's number in the emergency SMS, the actor id in the audit log --
    keys on the value being absent, and any non-empty string defeats all of them
    at once. So junk is not a name, not-a-name is None, and the fallbacks go on
    working.
    """
    if value is None:
        return None

    # NFC, not NFKC: NFKC rewrites Arabic presentation forms and ligatures into
    # different letters, which is exactly the rewriting this module refuses.
    text = unicodedata.normalize("NFC", value)
    text = _INVISIBLE.sub("", text)
    # \s covers the tab and newline left after the controls above, and folds a
    # run of them into the single space a person meant.
    text = _WHITESPACE.sub(" ", text).strip()

    if not text:
        return None
    if sum(1 for character in text if character.isalpha()) < _MINIMUM_LETTERS:
        return None
    return text
