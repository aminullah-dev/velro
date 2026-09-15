"""The staff console's search boxes, read the way the operator meant them.

No database: what a typed term means is decided in the domain, and the SQL
only applies it. The e2e module next door proves the wiring.
"""

from __future__ import annotations

import pytest

from domain.search import SearchTerm, normalise_business_number

STORED = "+93700123456"


class TestAPhoneNumberHoweverItWasTyped:
    @pytest.mark.parametrize("typed", [
        "0700123456",
        "+93700123456",
        "93700123456",
        "0093700123456",
        "0700 123 456",
        "0700-123-456",
        "(0700) 123 456",
        "+93 700 123 456",
        "۰۷۰۰۱۲۳۴۵۶",          # Persian / Pashto keyboard
        "٠٧٠٠١٢٣٤٥٦",          # Arabic keyboard
        "+۹۳ ۷۰۰ ۱۲۳ ۴۵۶",
        "0700۱۲۳456",          # a keyboard switched halfway through
    ])
    def test_finds_the_stored_number(self, typed: str) -> None:
        term = SearchTerm.parse(typed)
        assert term is not None
        assert term.phone_digits is not None
        assert term.phone_digits in STORED

    def test_a_fragment_is_still_a_phone_search(self) -> None:
        term = SearchTerm.parse("۱۲۳۴۵")
        assert term is not None and term.phone_digits == "12345"

    @pytest.mark.parametrize("typed", ["0", "07", "0093", "+"])
    def test_too_few_digits_are_not_a_phone_search(self, typed: str) -> None:
        term = SearchTerm.parse(typed)
        assert term is None or term.phone_digits is None


class TestANameOrAPlateIsNotAPhone:
    @pytest.mark.parametrize("typed", ["Rahim", "رحیم گل", "KBL 4567", "کابل ۴۵۶۷"])
    def test_letters_mean_it_is_not_a_phone(self, typed: str) -> None:
        term = SearchTerm.parse(typed)
        assert term is not None and term.phone_digits is None

    def test_the_text_keeps_the_letters_and_folds_the_digits(self) -> None:
        term = SearchTerm.parse("  کابل   ۴۵۶۷ ")
        assert term is not None and term.text == "کابل 4567"


class TestAPlate:
    @pytest.mark.parametrize("typed", ["kbl-۴۵۶۷", "KBL 4567", "kbl٤٥٦٧", "KBL-4567"])
    def test_every_spelling_has_one_key(self, typed: str) -> None:
        term = SearchTerm.parse(typed)
        assert term is not None and term.plate_key == "KBL4567"

    def test_nothing_alphanumeric_is_no_plate(self) -> None:
        term = SearchTerm.parse("--")
        assert term is not None and term.plate_key is None


class TestBlankAndWildcards:
    @pytest.mark.parametrize("typed", [None, "", "   ", "\t\n"])
    def test_a_blank_box_is_no_filter(self, typed: str | None) -> None:
        assert SearchTerm.parse(typed) is None

    def test_the_operators_wildcards_are_letters(self) -> None:
        term = SearchTerm.parse(r"50%_off\x")
        assert term is not None
        assert term.like_pattern == r"%50\%\_off\\x%"

    def test_an_ordinary_term_is_a_contains_pattern(self) -> None:
        term = SearchTerm.parse("Gul")
        assert term is not None and term.like_pattern == "%Gul%"


class TestANameTypedOnAnotherKeyboard:
    @pytest.mark.parametrize(("typed", "folded"), [
        ("كريمة علي", "%کریمه علی%"),      # Arabic keyboard: ك ة ي
        ("کریمه علی", "%کریمه علی%"),      # Persian keyboard: already folded
        ("يوسفى", "%یوسفی%"),              # yeh and alef maksura
    ])
    def test_the_name_pattern_folds_the_letters(self, typed: str, folded: str) -> None:
        term = SearchTerm.parse(typed)
        assert term is not None and term.name_pattern == folded

    def test_the_name_pattern_keeps_the_wildcards_as_letters(self) -> None:
        term = SearchTerm.parse(r"علي_50%\x")
        assert term is not None
        assert term.name_pattern == r"%علی\_50\%\\x%"

    def test_the_text_itself_is_not_folded(self) -> None:
        """What was typed is kept; only the name comparison folds."""
        term = SearchTerm.parse("كريم")
        assert term is not None and term.text == "كريم"
        assert term.like_pattern == "%كريم%"

    def test_the_sql_table_is_the_python_table(self) -> None:
        """translate(name, FROM, TO) in the database must fold exactly what
        fold_letters folds, letter for letter, or the two sides disagree."""
        from domain.text import LETTER_FOLDING_FROM, LETTER_FOLDING_TO, fold_letters

        assert len(LETTER_FOLDING_FROM) == len(LETTER_FOLDING_TO) > 0
        assert fold_letters(LETTER_FOLDING_FROM) == LETTER_FOLDING_TO
        assert {"ي", "ى", "ك", "ة"} <= set(LETTER_FOLDING_FROM)


class TestATripNumber:
    @pytest.mark.parametrize("typed", [
        "VLR-2026-000047",
        " vlr-2026-000047 ",
        "VLR-۲۰۲۶-۰۰۰۰۴۷",
        "vlr-٢٠٢٦-٠٠٠٠٤٧",
    ])
    def test_reads_as_the_stored_number(self, typed: str) -> None:
        assert normalise_business_number(typed) == "VLR-2026-000047"

    def test_is_otherwise_exact(self) -> None:
        """No guessing: a lookup that forgave a missing zero would open the
        wrong trip."""
        assert normalise_business_number("VLR-2026-47") == "VLR-2026-47"
