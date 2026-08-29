"""Import parsing and duplicate detection.

Pure functions, no database. What is tested here is the part that decides
whether two spellings are the same place -- and that decision is only ever a
proposal for a person to confirm (section 7).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from application.use_cases.import_villages import DUPLICATE_THRESHOLD, parse
from domain.text import comparison_key, normalise, similarity
from shared.errors import ValidationError


class TestParsing:
    def test_a_csv_becomes_rows(self) -> None:
        csv = (
            "district_code,name,alternative_names,latitude,longitude\n"
            "GRB-SYG,خیشکی,,35.125,68.77\n"
            "GRB-SYG,صدوار,سبزوار,,\n"
        ).encode()
        rows, problems = parse(csv, "villages.csv")
        assert not problems
        assert [r.name for r in rows] == ["خیشکی", "صدوار"]
        assert rows[1].aliases == ["سبزوار"]
        assert rows[0].latitude == Decimal("35.125")
        assert rows[1].latitude is None

    def test_row_numbers_point_at_the_spreadsheet_line(self) -> None:
        """An operator fixing a file needs the line number they can see."""
        csv = b"district_code,name\nGRB-SYG,alpha\nGRB-SYG,beta\n"
        rows, _ = parse(csv, "v.csv")
        assert [r.row_number for r in rows] == [2, 3]

    @pytest.mark.parametrize("separator", ["|", ";", ","])
    def test_aliases_accept_the_separators_spreadsheets_actually_use(
        self, separator: str
    ) -> None:
        # Quoted, because a bare comma is the CSV field separator -- an operator
        # using commas for aliases must quote the cell, and Excel does so.
        csv = (
            "district_code,name,alternative_names\n"
            f'GRB-SYG,دره‌قول‌خول,"خسرویه{separator}قول"\n'
        ).encode()
        rows, _ = parse(csv, "v.csv")
        assert rows[0].aliases == ["خسرویه", "قول"]

    def test_a_missing_required_column_is_refused_up_front(self) -> None:
        with pytest.raises(ValidationError) as exc:
            parse(b"name\nalpha\n", "v.csv")
        assert exc.value.code == "IMPORT_COLUMN_MISSING"
        assert exc.value.context["column"] == "district_code"

    def test_bad_rows_are_reported_not_silently_dropped(self) -> None:
        csv = (
            b"district_code,name,latitude\n"
            b"GRB-SYG,good,35.1\n"
            b",missing district,\n"
            b"GRB-SYG,,\n"
            b"GRB-SYG,bad coords,not-a-number\n"
        )
        rows, problems = parse(csv, "v.csv")
        assert [r.name for r in rows] == ["good", "bad coords"]
        reasons = {(p.column, p.reason) for p in problems}
        assert ("district_code", "missing") in reasons
        assert ("name", "missing") in reasons
        assert ("latitude", "not_a_number") in reasons

    def test_coordinates_outside_the_globe_are_refused(self) -> None:
        csv = b"district_code,name,latitude,longitude\nGRB-SYG,x,200,10\n"
        _, problems = parse(csv, "v.csv")
        assert any(p.reason == "out_of_range" for p in problems)

    def test_json_input_is_accepted(self) -> None:
        payload = b'[{"district_code":"GRB-SHW","name":"\\u067e\\u0644 \\u0645\\u062a\\u06a9"}]'
        rows, problems = parse(payload, "villages.json")
        assert not problems
        assert rows[0].district_code == "GRB-SHW"

    def test_a_byte_order_mark_does_not_corrupt_the_first_column(self) -> None:
        """Excel writes one, and it silently breaks the header name."""
        csv = "﻿district_code,name\nGRB-SYG,alpha\n".encode()
        rows, problems = parse(csv, "v.csv")
        assert not problems and rows[0].district_code == "GRB-SYG"


class TestNameMatching:
    def test_keyboard_variants_of_one_name_match(self) -> None:
        """Arabic yeh against Persian yeh, and a zero-width non-joiner."""
        assert similarity("سياه‌گرد", "سیاه گرد") == 1.0
        assert similarity("دره‌قول‌خول", "دره قول خول") >= DUPLICATE_THRESHOLD

    def test_a_structural_word_does_not_make_two_names_differ(self) -> None:
        assert comparison_key("قریه خیشکی") == comparison_key("خیشکی")

    def test_genuinely_different_names_stay_apart(self) -> None:
        for a, b in [("خیشکی", "چاریکار"), ("سیاه‌گرد", "شینواری"), ("کج", "ترکمن")]:
            assert similarity(a, b) < DUPLICATE_THRESHOLD, f"{a} vs {b}"

    def test_an_alternative_name_is_not_treated_as_the_same_name(self) -> None:
        """صدوار and سبزوار are one village under two names -- a fact a person
        supplies, not something the matcher may infer."""
        assert similarity("صدوار", "سبزوار") < DUPLICATE_THRESHOLD

    def test_pashto_letters_are_never_folded_away(self) -> None:
        """ټ ډ ړ ږ ښ ګ ڼ distinguish real words and must survive normalisation."""
        for letter in "ټډړږښګڼ":
            assert letter in normalise(f"کلی{letter}")

    def test_normalisation_never_rewrites_what_is_stored(self) -> None:
        """The comparison form is derived, never persisted in place of the name."""
        original = "دره‌قول‌خول"
        assert normalise(original) != original
        assert comparison_key(original) != original
