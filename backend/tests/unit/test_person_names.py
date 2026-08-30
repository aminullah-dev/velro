"""What counts as a name.

This decides what is stored under a person's name for the whole product: the
heading on an offer card that a woman reads before choosing whose car to get
into, the line in the emergency SMS, the actor on an audit entry that settles a
dispute about money. It runs with no database and no fixtures, which is the
point -- it is a rule, not a query.

The characters below are written as escapes and named constants rather than
pasted in, because the ones that matter here are invisible by construction: a
literal U+202E in a test file is indistinguishable from nothing at all.
"""

from __future__ import annotations

import pytest

from domain.person_names import clean

ZWNJ = "‌"  # zero-width non-joiner
RLM = "‏"  # right-to-left mark
RLO = "‮"  # right-to-left override
BOM = "﻿"


class TestWhatIsKept:
    def test_a_name_survives_untouched(self) -> None:
        assert clean("محمد") == "محمد"
        assert clean("حاجی گل احمد سروری") == "حاجی گل احمد سروری"

    def test_one_word_is_a_name(self) -> None:
        """Many people here have a given name and no family name at all.

        A rule demanding two words would reject them, and the person it rejects
        cannot argue with a form.
        """
        assert clean("زرغونه") == "زرغونه"

    def test_a_two_letter_name_is_a_name(self) -> None:
        """گل is a real name. This is why the rule counts letters and not
        characters: a length of three would have thrown it away."""
        assert clean("گل") == "گل"

    def test_padding_and_runs_of_space_are_tidied(self) -> None:
        assert clean("  محمد  ") == "محمد"
        assert clean("محمد\t\n  نعیم") == "محمد نعیم"

    def test_the_zero_width_non_joiner_is_left_alone(self) -> None:
        """The single most important character in this module.

        domain.text deletes it, correctly, for comparing village spellings.
        Doing that to a person would store نجیبالله for a man who typed
        نجیب‌الله. They are two different spellings and they stay two.
        """
        typed = "نجیب" + ZWNJ + "الله"
        assert clean(typed) == typed
        assert ZWNJ in clean(typed)
        assert clean(typed) != clean("نجیب الله")

    def test_no_letter_is_ever_folded(self) -> None:
        """Unlike place names, which fold ی/ي and ک/ك to find duplicates.

        A person is entitled to the spelling they gave.
        """
        assert clean("عليرضا") == "عليرضا"  # Arabic yeh, kept as typed
        assert clean("علیرضا") == "علیرضا"  # Persian yeh, also kept
        assert clean("عليرضا") != clean("علیرضا")

    def test_the_allah_ligature_is_not_expanded(self) -> None:
        """Why NFC and not NFKC.

        عبدالله is commonly typed as عبدا plus the single-character ligature
        U+FDF2. NFKC expands that ligature to الله, which gives عبداالله -- a
        doubled alef, and a misspelling of a man's name that he never made.
        NFC leaves the character he typed alone, and it renders correctly.

        Without this test the NFC/NFKC choice was a comment with nothing
        holding it in place, and swapping them broke nothing.
        """
        typed = "\u0639\u0628\u062f\u0627\ufdf2"
        assert clean(typed) == typed
        assert "\ufdf2" in clean(typed)

    def test_pashto_letters_are_untouched(self) -> None:
        assert clean("ښکلی") == "ښکلی"
        assert clean("ګل ولي") == "ګل ولي"


class TestWhatIsRemoved:
    @pytest.mark.parametrize("mark", [RLM, RLO, BOM, "‎", "⁦"])
    def test_invisible_marks_are_stripped(self, mark: str) -> None:
        assert clean(mark + "محمد" + mark) == "محمد"

    def test_control_characters_are_stripped(self) -> None:
        assert clean("\x00محمد\x07") == "محمد"


class TestWhatIsNotAName:
    """The reason this returns None instead of raising.

    The field is optional wherever it appears, and the person filling it is
    often standing at a station with a keyboard over half the screen and the
    button he wants behind the form. Some will type one letter to get past it.

    Storing that letter would be the worst outcome available: every fallback in
    the product keys on the name being absent -- the driver's number in the
    emergency SMS, the actor id in the audit log -- and any non-empty string
    defeats all of them at once. So it is not stored, and the fallbacks live.
    """

    @pytest.mark.parametrize(
        "typed", ["", "   ", "G", "م", ".", "..", "-", "1", "123", "!!", ZWNJ, RLO]
    )
    def test_junk_is_not_a_name(self, typed: str) -> None:
        assert clean(typed) is None

    def test_none_stays_none(self) -> None:
        assert clean(None) is None

    def test_a_name_with_a_digit_in_it_is_still_a_name(self) -> None:
        """The rule is a floor, not a filter. Nothing here tries to decide
        whether a real name looks real -- that is not knowable, and a wrong
        guess locks somebody out of their own account."""
        assert clean("محمد ۲") == "محمد ۲"


def test_cleaning_is_idempotent() -> None:
    """A stored name re-submitted unchanged must not drift."""
    for typed in ["محمد", "حاجی گل احمد", "نجیب" + ZWNJ + "الله", "ښکلی"]:
        once = clean(typed)
        assert clean(once) == once
