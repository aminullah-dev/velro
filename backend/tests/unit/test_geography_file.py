"""The file that is the only copy of four hundred villages.

Four hundred and twenty-seven villages arrived through one spreadsheet
upload whose file was never kept, and their coordinates come from one
person pointing at a map, hundreds of times. Both lived in a single
Postgres database on a single laptop until this file existed. What these
hold still is the property that makes it a backup rather than a report:
what comes out can be put back.
"""

from __future__ import annotations

from decimal import Decimal

from infrastructure.geo_coordinates import FIELDS, Place, read, write


def village(code, lat=None, lon=None, name="قریه", district="GRB-SYG"):
    return Place("village", code, name, district,
                 Decimal(lat) if lat else None, Decimal(lon) if lon else None)


def station(code, lat=None, lon=None):
    return Place("station", code, f"ایستگاه {code}", "GRB-SYG",
                 Decimal(lat) if lat else None, Decimal(lon) if lon else None)


class TestRoundTrip:
    def test_what_goes_in_comes_back_out(self, tmp_path):
        original = [
            village("GRB-SYG-001", "35.001181", "68.797929"),
            village("GRB-SYG-002"),
            station("GRB-SYG-001-S1"),
        ]
        path = write(original, tmp_path / "geography.csv")
        assert read(path) == sorted(
            original, key=lambda p: (0 if p.kind == "village" else 1, p.code)
        )

    def test_an_unplaced_village_keeps_its_name_and_district(self, tmp_path):
        path = write([village("GRB-SHW-042", name="پل متک", district="GRB-SHW")],
                     tmp_path / "g.csv")
        back = read(path)[0]
        assert back.name == "پل متک"
        assert back.district_code == "GRB-SHW"
        assert back.latitude is None and back.longitude is None

    def test_coordinates_survive_to_the_metre(self, tmp_path):
        # Six decimals is about ten centimetres; anything that rounds a
        # coordinate silently is losing somebody's afternoon.
        path = write([village("GRB-SYG-009", "34.994592", "68.760780")],
                     tmp_path / "g.csv")
        back = read(path)[0]
        assert back.latitude == Decimal("34.994592")
        assert back.longitude == Decimal("68.760780")


class TestOrder:
    def test_villages_are_written_before_their_stations(self, tmp_path):
        # Load-bearing: a station cannot be created before the village that
        # owns it, and "station" sorts before "village" alphabetically --
        # which is exactly how the first rebuild produced 427 villages and
        # 12 stations.
        path = write(
            [station("GRB-SYG-001-S1"), village("GRB-SYG-001")], tmp_path / "g.csv"
        )
        kinds = [p.kind for p in read(path)]
        assert kinds == ["village", "station"]

    def test_rows_are_sorted_so_a_diff_shows_only_what_changed(self, tmp_path):
        path = write(
            [village("GRB-SYG-010"), village("GRB-SYG-002"), village("GRB-SHA-001")],
            tmp_path / "g.csv",
        )
        assert [p.code for p in read(path)] == [
            "GRB-SHA-001", "GRB-SYG-002", "GRB-SYG-010",
        ]


class TestAbsence:
    def test_a_missing_file_is_a_normal_state(self, tmp_path):
        assert read(tmp_path / "not-here.csv") == []

    def test_the_header_is_the_documented_one(self, tmp_path):
        path = write([village("GRB-SYG-001")], tmp_path / "g.csv")
        assert path.read_text(encoding="utf-8").splitlines()[0] == ",".join(FIELDS)


class TestTheCommittedFile:
    """The real file, held to the promises the rebuild depends on."""

    def committed(self):
        import pytest

        from infrastructure.geo_coordinates import read as read_committed

        places = read_committed()
        if not places:
            pytest.skip("no geography.csv committed yet")
        return places

    def test_every_station_has_the_village_that_owns_it(self):
        places = self.committed()
        villages = {p.code for p in places if p.kind == "village"}
        orphans = [
            p.code for p in places
            if p.kind == "station" and p.code.rsplit("-S", 1)[0] not in villages
        ]
        assert not orphans, f"stations whose village is absent: {orphans[:5]}"

    def test_no_two_rows_claim_the_same_code(self):
        seen = set()
        for place in self.committed():
            key = (place.kind, place.code)
            assert key not in seen, f"duplicate row: {key}"
            seen.add(key)

    def test_every_placed_point_is_inside_the_region(self):
        # The same box the placer refuses outside of. A coordinate that
        # escaped it is a typo nobody would ever see again.
        for place in self.committed():
            if place.latitude is None:
                continue
            assert 34.0 <= float(place.latitude) <= 36.0, place.code
            assert 67.5 <= float(place.longitude) <= 70.0, place.code
