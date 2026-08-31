"""A boarding code typed on an Afghan keyboard.

The code a passenger holds up is generated from "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
at length four, so 68% of codes contain at least one digit. It is shown to her
in Latin. The driver reads it off her screen and types it on his own keyboard,
which on a Persian or Pashto layout emits U+06F0-U+06F9 -- ۲, not 2.

The comparison was `upper(stored) == typed.strip().upper()`, and Python's
upper() maps no digits at all. So for two thirds of every booking VELRO has
ever made, a driver on the keyboard most of his passengers use could type the
code perfectly and never be let in. The app now folds on entry; this is the
other half, because the handsets already in the valley carry the build that
did not.
"""

from __future__ import annotations

import pytest

from domain.text import normalise_digits

EASTERN = "۰۱۲۳۴۵۶۷۸۹"
ARABIC = "٠١٢٣٤٥٦٧٨٩"


class TestFolding:
    @pytest.mark.parametrize("typed,expected", [
        ("۲۴۷۹", "2479"),
        ("٢٤٧٩", "2479"),
        ("B24Z", "B24Z"),
        ("B۲۴Z", "B24Z"),
    ])
    def test_a_code_reads_the_same_whichever_keyboard_typed_it(
        self, typed: str, expected: str
    ) -> None:
        assert normalise_digits(typed) == expected

    def test_every_eastern_digit_is_mapped(self) -> None:
        assert normalise_digits(EASTERN) == "0123456789"
        assert normalise_digits(ARABIC) == "0123456789"

    def test_letters_are_left_exactly_alone(self) -> None:
        """Not `normalise`: a code is not a village name. Lowercasing it,
        stripping its punctuation or folding its diacritics would each break a
        different thing."""
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ"
        assert normalise_digits(alphabet) == alphabet

    def test_the_generated_alphabet_survives_a_round_trip(self) -> None:
        # Every character a real code can contain, unchanged.
        from infrastructure.services.codes import _UNAMBIGUOUS
        assert normalise_digits(_UNAMBIGUOUS) == _UNAMBIGUOUS
