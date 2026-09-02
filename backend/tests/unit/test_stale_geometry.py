"""A precomputed road that no longer starts where its station does.

The geometry file is fetched once at a desk and committed, which is what
makes journeys free at runtime. The price is that a station corrected
afterwards leaves its leg describing somewhere else -- and the first
operator session moved one fourteen kilometres. So the reader checks, and
prefers an honest corridor slice over a confident wrong line.
"""

from __future__ import annotations

from ui.api.mapdata import _STALE_ENDPOINT_M, _leg_matches

KHISHKI = (68.79793, 35.00118)      # where the operator says it is
OLD_KHISHKI = (68.770, 35.125)      # where the seed guessed
CHARIKAR = (69.1711, 35.0128)


def leg(a, b):
    return {"from_lonlat": list(a), "to_lonlat": list(b), "points": [], "duration_s": 1}


class TestFresh:
    def test_a_leg_about_these_two_places_is_used(self):
        assert _leg_matches(leg(KHISHKI, CHARIKAR), KHISHKI, CHARIKAR) is True

    def test_a_few_metres_of_rounding_is_not_drift(self):
        nudged = (KHISHKI[0] + 0.0009, KHISHKI[1])   # ~80 m
        assert _leg_matches(leg(nudged, CHARIKAR), KHISHKI, CHARIKAR) is True

    def test_a_reversed_leg_is_matched_end_for_end(self):
        assert _leg_matches(
            leg(CHARIKAR, KHISHKI), KHISHKI, CHARIKAR, reversed_=True
        ) is True


class TestStale:
    def test_a_leg_from_before_the_correction_is_refused(self):
        assert _leg_matches(leg(OLD_KHISHKI, CHARIKAR), KHISHKI, CHARIKAR) is False

    def test_drift_at_either_end_is_enough_to_refuse(self):
        moved_far_end = (CHARIKAR[0] + 0.05, CHARIKAR[1])
        assert _leg_matches(leg(KHISHKI, moved_far_end), KHISHKI, CHARIKAR) is False

    def test_a_reversed_stale_leg_is_refused_too(self):
        assert _leg_matches(
            leg(CHARIKAR, OLD_KHISHKI), KHISHKI, CHARIKAR, reversed_=True
        ) is False


class TestOlderFiles:
    def test_a_leg_with_no_endpoints_recorded_is_trusted(self):
        # Written before this check existed. Refusing it would erase every
        # line rather than admit one uncertainty.
        assert _leg_matches({"points": []}, KHISHKI, CHARIKAR) is True

    def test_the_tolerance_is_stated_not_guessed(self):
        assert _STALE_ENDPOINT_M == 500
