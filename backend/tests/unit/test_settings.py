"""How a stored setting becomes a Python value.

Section 105 says no operational number is hard-coded: the commission rate, the
OTP length, the required documents and the emergency numbers are all rows. That
makes this function load-bearing — it decides what every one of those rows
means, and a mistake here is wrong for every user at once, from a database that
reads correctly to anyone who looks at it.
"""

from __future__ import annotations

import pytest

from infrastructure.services.settings import DEFAULTS, _unwrap, wrap


class TestUnwrap:
    def test_a_wrapped_value_comes_back_as_itself(self) -> None:
        for value in ("93", 1000, True, ["A", "B"], None):
            assert _unwrap(wrap(value)) == value

    def test_a_numeric_looking_string_stays_a_string(self) -> None:
        """The bug this test exists for.

        `_unwrap` used to run json.loads over a bare string, so a setting whose
        value happened to look like a number changed type on the way out. The
        country code "93" became the integer 93, and every get_str for it
        raised SETTING_TYPE_INVALID -- for every user at once, from a row that
        reads perfectly well in psql.
        """
        assert _unwrap("93") == "93"
        assert isinstance(_unwrap("93"), str)
        assert _unwrap("1") == "1"
        assert _unwrap("119") == "119"

    def test_a_boolean_looking_string_stays_a_string(self) -> None:
        assert _unwrap("true") == "true"
        assert isinstance(_unwrap("true"), str)

    def test_a_phone_number_survives(self) -> None:
        assert _unwrap("+93700000000") == "+93700000000"

    def test_text_that_is_plainly_a_container_is_still_parsed(self) -> None:
        """The one case where keeping the string would be the surprise."""
        assert _unwrap('["119", "100"]') == ["119", "100"]
        assert _unwrap('{"a": 1}') == {"a": 1}

    def test_malformed_container_text_is_left_alone(self) -> None:
        """Better a visibly wrong string than an exception on a settings read."""
        assert _unwrap("[not json") == "[not json"

    def test_a_wrapper_is_only_a_wrapper_when_that_is_all_it_is(self) -> None:
        """A stored object that happens to have a 'v' key is not an envelope."""
        stored = {"v": 1, "unit": "minor"}
        assert _unwrap(stored) == stored


class TestDefaults:
    @pytest.mark.parametrize("key", sorted(DEFAULTS))
    def test_every_default_survives_a_round_trip(self, key: str) -> None:
        """What seeding writes is what reading gives back.

        scripts/seed.py writes each default through `wrap`, so this is the exact
        path a fresh database takes.
        """
        assert _unwrap(wrap(DEFAULTS[key])) == DEFAULTS[key]

    def test_the_country_code_is_a_string_and_not_a_number(self) -> None:
        """Leading zeros matter in a country code, and get_str demands a string."""
        assert isinstance(DEFAULTS["auth.default_country_code"], str)
