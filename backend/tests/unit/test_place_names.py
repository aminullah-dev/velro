"""What counts as a place name.

A name kept here is shown to every passenger nearby and printed on the driver's
board, so the rule has two duties that pull against each other: refuse
anything that points at a household or a person, and never refuse a real
place. The second is proven against the master geography file itself -- a
filter that turns away one genuine village would teach its people that VELRO
does not know where they live.

Characters that matter and cannot be seen are written as escapes.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from domain.places import assert_allowed, refusal
from shared import error_codes
from shared.errors import ValidationError

ZWNJ = "‌"
EZAFE_HAMZA = "ٔ"  # the hamza above in "خانهٔ"

GEOGRAPHY = Path(__file__).resolve().parents[2] / "resources" / "geo" / "geography.csv"


class TestRealPlacesAreKept:
    @pytest.mark.parametrize(
        "name",
        [
            "خیشکی",
            "قلعه نو",
            "ده" + ZWNJ + "نو",
            "شیخ" + ZWNJ + "علی",
            "بازار شیخ" + ZWNJ + "علی",
            "چاریکار",
            "سبزوار",
            "مسجد جامع قلعه نو",   # a generic word beside a real name
            "شفاخانه غوربند",       # a hospital is not a home: "شفا" is not personal
            "Charikar",
        ],
    )
    def test_a_place_is_a_place(self, name: str) -> None:
        assert refusal(name) is None

    def test_every_name_in_the_master_file_is_accepted(self) -> None:
        """The one test that stops the filter from growing teeth.

        Every village, station and destination name VELRO knows. If a word is
        ever added to the lists in domain.places that also happens to be a
        village, this is where it shows -- before a passenger in that village
        is told their home is not a place.
        """
        with GEOGRAPHY.open(encoding="utf-8") as handle:
            names = [row["name"].strip() for row in csv.DictReader(handle) if row["name"].strip()]
        assert len(names) > 400, "the master file should hold every Ghorband village"
        refused = [(name, refusal(name)) for name in names if refusal(name) is not None]
        assert not refused, f"real places refused: {refused}"

    def test_the_stored_name_is_what_was_typed(self) -> None:
        """Only invisible characters are removed; no letter is folded."""
        typed = "  ده" + ZWNJ + "نو  "
        assert assert_allowed(typed) == "ده" + ZWNJ + "نو"


class TestHouseholdsAndPeopleAreRefused:
    @pytest.mark.parametrize(
        "name",
        [
            "خانه",
            "خانه" + EZAFE_HAMZA + " احمد",
            "خانه" + ZWNJ + "ی ما",
            "منزل",
            "کور",
            "زما کور",
            "دکان کاکا",
            "دفتر",
            "خانه" + ZWNJ + "ها",
            "home",
            "My house",
        ],
    )
    def test_a_household_is_refused(self, name: str) -> None:
        assert refusal(name) == "personal"

    @pytest.mark.parametrize("name", ["0799123456", "۰۷۹۹۱۲۳۴۵۶", "کوچه ۱۲"])
    def test_a_number_is_refused(self, name: str) -> None:
        """A phone number is a person; a house number is a door."""
        assert refusal(name) == "digits"

    def test_contact_details_are_refused(self) -> None:
        assert refusal("someone@example.com") == "contact"

    @pytest.mark.parametrize("name", ["مسجد", "قریه", "بازار", "اینجا", "دلته", "here"])
    def test_a_kind_of_place_alone_is_not_a_place(self, name: str) -> None:
        assert refusal(name) == "generic"

    @pytest.mark.parametrize("name", ["", "   ", "-", "آ", None])
    def test_nothing_is_not_a_name(self, name: str | None) -> None:
        assert refusal(name) == "empty"

    def test_a_description_is_refused(self) -> None:
        assert refusal("نزدیک پل بزرگ کنار دریا پشت مکتب") == "too_long"
        assert refusal("ق" * 61) == "too_long"


def test_the_refusal_travels_with_the_error() -> None:
    with pytest.raises(ValidationError) as caught:
        assert_allowed("خانه")
    assert caught.value.code == error_codes.PLACE_NAME_NOT_ALLOWED
    assert caught.value.context.get("reason") == "personal"


def test_one_name_typed_three_ways_is_one_key() -> None:
    from domain.places import place_key

    assert place_key("باغ" + ZWNJ + "بالا") == place_key("باغ بالا") == place_key("باغبالا")
    assert place_key("قریه خیشکی") == place_key("خیشکی")
    assert place_key("خیشکی") != place_key("قلعه نو")
