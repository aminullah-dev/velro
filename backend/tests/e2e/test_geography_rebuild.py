"""Rebuilding the geography from the file, against a real database.

The unit tests hold the file's shape; this holds the promise. A database
that has only been seeded is missing four hundred villages -- the state of
every machine except the one they were typed into -- and importing must
produce what the file describes and then change nothing when run again.

Everything here rolls back: the suite's own database is left exactly as it
was found.
"""

from __future__ import annotations

import pytest

from infrastructure.geo_coordinates import apply, gather, read
from ui.api import deps


@pytest.fixture()
def places():
    committed = read()
    if not committed:
        pytest.skip("no geography.csv committed yet")
    return committed


class TestRebuilding:
    def test_a_seeded_database_gains_the_whole_geography(self, client, places):
        with deps._session_factory()() as session:
            result = apply(session, places)

            # Everything the file describes is now present and correct.
            rebuilt = {(p.kind, p.code): p for p in gather(session)}
            for place in places:
                key = (place.kind, place.code)
                assert key in rebuilt, f"{key} did not land"
                if place.latitude is not None:
                    assert rebuilt[key].latitude == place.latitude
                    assert rebuilt[key].longitude == place.longitude

            assert result.skipped == [], result.skipped
            session.rollback()

    def test_importing_a_second_time_changes_nothing(self, client, places):
        with deps._session_factory()() as session:
            apply(session, places)
            again = apply(session, places)
            session.rollback()

        assert again.created == []
        assert again.placed == []
        assert again.corrected == []
        assert again.skipped == []
        assert len(again.unchanged) == sum(
            1 for p in places if p.latitude is not None
        )

    def test_a_station_arrives_standing_with_its_village(self, client, places):
        placed = next(
            (p for p in places if p.kind == "village" and p.latitude is not None),
            None,
        )
        if placed is None:
            pytest.skip("nothing placed yet")
        with deps._session_factory()() as session:
            apply(session, places)
            from sqlalchemy import text as sql

            station = session.execute(sql(
                "SELECT s.latitude, s.longitude FROM stations s "
                "JOIN villages v ON v.id = s.village_id "
                "WHERE v.code = :code AND s.deleted_at IS NULL LIMIT 1"
            ), {"code": placed.code}).first()
            session.rollback()
        assert station is not None
        assert station.latitude == placed.latitude, (
            "a rebuilt station must stand where its village does"
        )
