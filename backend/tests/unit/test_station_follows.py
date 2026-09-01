"""When a corrected village drags its station along, and when it does not.

The first real correction an operator made -- خیشکی, fourteen kilometres --
moved the village and left the station behind, because the rule said a
station with a point of its own keeps it. That was meant to protect a point
somebody chose deliberately, and instead it protected a sample value from
the person who knows the ground. This is that rule, restated and pinned.
"""

from __future__ import annotations

from decimal import Decimal

from ui.api.routers.admin import STATION_FOLLOWS_WITHIN_M, station_follows

VILLAGE_WAS = (Decimal("35.125"), Decimal("68.770"))


class TestFollows:
    def test_a_station_with_no_point_always_takes_the_villages(self):
        assert station_follows(None, VILLAGE_WAS) is True
        assert station_follows((None, None), VILLAGE_WAS) is True

    def test_a_station_with_no_point_follows_even_a_first_placement(self):
        # No previous village point either: this is the ordinary case of
        # placing a village that has never been placed.
        assert station_follows((None, None), None) is True

    def test_a_station_standing_with_its_village_follows_the_correction(self):
        # The same spot, to the metre and to a few hundred metres.
        assert station_follows(VILLAGE_WAS, VILLAGE_WAS) is True
        assert station_follows(
            (Decimal("35.1260"), Decimal("68.7715")), VILLAGE_WAS
        ) is True


class TestStaysPut:
    def test_a_station_placed_deliberately_elsewhere_is_left_alone(self):
        # Two kilometres away: not where the village stood, so somebody put
        # it there on purpose.
        assert station_follows(
            (Decimal("35.1430"), VILLAGE_WAS[1]), VILLAGE_WAS
        ) is False

    def test_a_station_with_a_point_and_a_village_with_no_history_stays(self):
        # Nothing to compare against: the safe answer is to touch nothing.
        assert station_follows(VILLAGE_WAS, None) is False

    def test_the_threshold_is_a_kilometre_not_a_guess(self):
        assert STATION_FOLLOWS_WITHIN_M == 1_000
