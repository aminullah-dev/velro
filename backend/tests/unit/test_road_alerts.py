"""The curvature scan, fed roads whose shape is known by construction.

The thresholds are tuned data, so these do not pin exact zone counts on the
real corridors -- they pin the property: straight roads say nothing, a
switchback says something, and a stack of switchbacks says it once.
"""

from __future__ import annotations

from ui.api.mapdata import CAUTION_ZONES, curve_zones, road_alerts


def _road(*steps: tuple[float, float], start=(68.5, 35.0), n=8) -> list[list[float]]:
    """Straight segments of n points each; steps are (dlon, dlat) per point."""
    points = [list(start)]
    for dlon, dlat in steps:
        for _ in range(n):
            last = points[-1]
            points.append([last[0] + dlon, last[1] + dlat])
    return points


STEP = 0.0005  # ~45 m of longitude per point at this latitude


class TestStraight:
    def test_a_straight_road_has_nothing_to_say(self):
        assert curve_zones(_road((STEP, 0), (STEP, 0), n=40)) == []

    def test_a_gentle_drift_stays_quiet(self):
        # A long shallow arc: one degree of heading per point never
        # accumulates enough turn inside the window to matter.
        import math
        points, heading = [[68.5, 35.0]], 0.0
        for _ in range(120):
            heading += math.radians(1.0)
            last = points[-1]
            points.append([last[0] + STEP * math.cos(heading),
                           last[1] + STEP * math.sin(heading)])
        assert curve_zones(points) == []


class TestBends:
    def test_a_hairpin_is_announced(self):
        # East, then sharply back west-north: a 135-degree turn in one place.
        zones = curve_zones(_road((STEP, 0), (-STEP, STEP)))
        assert len(zones) == 1
        assert zones[0]["kind"] == "curve"
        assert zones[0]["message_key"] == "road.alert.curve"
        assert zones[0]["radius_m"] >= 250

    def test_a_switchback_stack_is_one_zone_not_five(self):
        zones = curve_zones(
            _road((STEP, 0), (0, STEP), (-STEP, 0), (0, STEP), (STEP, 0), n=4)
        )
        assert len(zones) == 1

    def test_two_far_apart_bends_are_two_zones(self):
        # East, corner, a long straight run north, corner, east again: two
        # right-angle bends with two kilometres of quiet between them.
        zones = curve_zones(_road((STEP, 0), (0, STEP), (STEP, 0), n=40))
        assert len(zones) == 2


class TestTheRealRoad:
    def test_the_ghorband_corridor_earns_its_reputation(self):
        # The operator's words: mountainous, riverside. If the scan found
        # nothing on this road, the scan would be wrong.
        alerts = road_alerts()
        curves = [a for a in alerts if a["kind"] == "curve"]
        assert len(curves) >= 10
        for alert in alerts:
            assert set(alert) == {
                "latitude", "longitude", "radius_m", "kind", "message_key"
            }

    def test_the_hand_placed_siahgird_stretch_is_present(self):
        assert any(
            a["kind"] == "caution" and abs(a["latitude"] - 34.998) < 0.01
            for a in road_alerts()
        )
        # And the list object itself is not shared mutable state.
        assert road_alerts() is not CAUTION_ZONES
