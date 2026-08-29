"""Perso-Arabic text normalisation.

Village names arrive from spreadsheets typed on different keyboards across
twenty years. The same place is written with Arabic yeh or Persian yeh, Arabic
kaf or Persian kaf, with or without a zero-width non-joiner, with or without
diacritics, with Eastern Arabic-Indic or Latin digits.

Normalisation exists *only* to compare names during duplicate detection. The
stored name is always what the operator typed -- normalising for storage would
quietly rewrite people's place names, which is not ours to do.
"""

from __future__ import annotations

import re
import unicodedata

# Characters that differ between Arabic, Persian and Pashto keyboards but denote
# the same letter for the purpose of comparing an Afghan place name.
_LETTER_FOLDING = str.maketrans(
    {
        "ي": "ی", "ى": "ی", "ئ": "ی",   # yeh forms
        "ك": "ک",                                            # kaf
        "أ": "ا", "إ": "ا", "آ": "ا",    # alef forms
        "ٱ": "ا",
        "ة": "ه", "ۀ": "ه",                        # teh marbuta, heh+yeh
        "ؤ": "و",
    }
)

# Pashto-specific consonants are deliberately NOT folded into their Persian
# lookalikes: ټ ډ ړ ږ ښ ګ ڼ distinguish real, different words. Nor are the
# Pashto vowels ې and ۍ. The yeh forms above ARE folded, which is wrong for
# Pashto morphology in general but right here: the same village is written with
# ي and ی by different clerks, and this function only ever *proposes* a
# duplicate for a human to confirm.

_DIACRITICS = re.compile(r"[ً-ْٰـ]")
_JOINERS = re.compile(r"[​-‏‪-‮⁦-⁩]")
_WHITESPACE = re.compile(r"\s+")
_NOISE = re.compile(r"[^\w\s]", re.UNICODE)

_EASTERN_DIGITS = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹"
    "٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)

# Words that carry no distinguishing power in an Afghan village name.
_STOPWORDS = frozenset({"قریه", "ده", "کلی", "village"})


def normalise(value: str) -> str:
    """Fold a name to its comparison form. Never stored, never displayed."""
    text = unicodedata.normalize("NFKC", value).strip().lower()
    text = _JOINERS.sub("", text)
    text = _DIACRITICS.sub("", text)
    text = text.translate(_LETTER_FOLDING)
    text = text.translate(_EASTERN_DIGITS)
    text = _NOISE.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


def comparison_key(value: str) -> str:
    """Normalised form with structural stopwords removed, for duplicate matching."""
    parts = [p for p in normalise(value).split(" ") if p and p not in _STOPWORDS]
    return " ".join(parts) if parts else normalise(value)


def similarity(left: str, right: str) -> float:
    """Token-aware ratio in [0.0, 1.0]. Used only to *propose* duplicates.

    Deliberately conservative and never authoritative: section 7 of the product
    specification requires that similar names are never merged without proof, so
    this returns a score for a human to act on and nothing else.
    """
    a, b = comparison_key(left), comparison_key(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0

    a_tokens, b_tokens = set(a.split()), set(b.split())
    jaccard = (
        len(a_tokens & b_tokens) / len(a_tokens | b_tokens) if a_tokens & b_tokens else 0.0
    )
    return max(jaccard, _bigram_dice(a, b))


def _bigram_dice(a: str, b: str) -> float:
    def bigrams(s: str) -> set[str]:
        squeezed = s.replace(" ", "")
        return {squeezed[i : i + 2] for i in range(len(squeezed) - 1)}

    left, right = bigrams(a), bigrams(b)
    if not left or not right:
        return 0.0
    return 2 * len(left & right) / (len(left) + len(right))


def to_eastern_digits(value: str) -> str:
    """Display helper for Dari and Pashto prose. Never applied to stored data."""
    return value.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
