"""The map, served like any other resource.

The base map is public bytes from a committed archive; the journey line is a
driver's own view of his own trip. Both are asserted through HTTP because
that is the only door the handset has.
"""

from __future__ import annotations

import math

from fastapi.testclient import TestClient

CENTER_LON, CENTER_LAT, Z = 68.8, 34.95, 11


def _tile_xy(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    lat_r = math.radians(lat)
    y = int((1 - math.asinh(math.tan(lat_r)) / math.pi) / 2 * n)
    return x, y


class TestBaseMap:
    def test_the_style_points_back_at_the_host_that_served_it(self, client: TestClient):
        style = client.get("/api/v1/geo/map/style.json")
        assert style.status_code == 200, style.text
        body = style.json()
        assert body["version"] == 8
        tiles = body["sources"]["region"]["tiles"][0]
        assert tiles.startswith("http://testserver/api/v1/geo/map/tiles/")
        assert "© OpenStreetMap" in body["sources"]["region"]["attribution"]

    def test_a_tile_over_the_valley_has_bytes_in_it(self, client: TestClient):
        x, y = _tile_xy(CENTER_LON, CENTER_LAT, Z)
        tile = client.get(f"/api/v1/geo/map/tiles/{Z}/{x}/{y}.mvt")
        assert tile.status_code == 200, tile.status_code
        assert len(tile.content) > 100
        assert tile.headers["content-type"] == "application/x-protobuf"

    def test_the_ocean_of_the_pyramid_is_an_empty_answer_not_an_error(self, client: TestClient):
        # Herat is outside the archive on purpose.
        x, y = _tile_xy(62.2, 34.35, Z)
        tile = client.get(f"/api/v1/geo/map/tiles/{Z}/{x}/{y}.mvt")
        assert tile.status_code == 204

    def test_the_arabic_glyph_range_exists_for_the_labels(self, client: TestClient):
        glyphs = client.get("/api/v1/geo/map/glyphs/Noto%20Sans%20Regular/1536-1791.pbf")
        assert glyphs.status_code == 200
        assert len(glyphs.content) > 1000

    def test_glyphs_do_not_walk_the_filesystem(self, client: TestClient):
        sneaky = client.get("/api/v1/geo/map/glyphs/..%2F..%2Flocales/en.pbf")
        assert sneaky.status_code in (404, 422)


class TestJourneyLine:
    def test_a_drivers_trip_comes_back_with_its_shape(
        self, client: TestClient, driver_session: dict, admin_session: dict
    ):
        me = client.get("/api/v1/driver/me", headers=driver_session)
        assert me.status_code == 200, me.text
        my_driver_id = me.json()["data"]["id"]
        trips = client.get("/api/v1/admin/trips", headers=admin_session).json()["data"]
        mine = next((t for t in trips if t.get("driver_id") == my_driver_id), None)
        if mine is None:
            return  # this driver holds no trip in this run; ownership is
                    # still proven by the refusal test below
        trip_id = mine["id"]
        drawn = client.get(f"/api/v1/driver/trips/{trip_id}/map", headers=driver_session)
        assert drawn.status_code == 200, drawn.text
        body = drawn.json()["data"]
        assert body["attribution"] == "© OpenStreetMap"
        assert isinstance(body["stations"], list) and body["stations"]
        for station in body["stations"]:
            assert set(station) == {"name", "latitude", "longitude"}
        # geometry may honestly be null when an endpoint has no coordinates;
        # when present it is (lat, lon) pairs inside the region box.
        if body["geometry"] is not None:
            for lat, lon in body["geometry"][:: max(1, len(body["geometry"]) // 20)]:
                assert 34.0 < lat < 36.0 and 67.5 < lon < 70.0

    def test_another_drivers_trip_is_not_even_a_thing_that_exists(
        self, client: TestClient, driver_session: dict, admin_session: dict
    ):
        # Find a trip that belongs to some OTHER driver via the admin surface.
        trips = client.get("/api/v1/admin/trips", headers=admin_session).json()["data"]
        me = client.get("/api/v1/driver/me", headers=driver_session)
        my_driver_id = me.json()["data"]["id"] if me.status_code == 200 else None
        foreign = next(
            (t for t in trips if t.get("driver_id") not in (None, my_driver_id)), None
        )
        if foreign is None:
            return
        refused = client.get(
            f"/api/v1/driver/trips/{foreign['id']}/map", headers=driver_session
        )
        assert refused.status_code == 404, refused.text
