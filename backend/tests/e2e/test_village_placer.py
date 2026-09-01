"""The pin, from the operator's finger to two tables.

The placer is data entry for someone with local knowledge and no patience
for GIS, so what these hold still is the contract that makes tap-tap-tap
safe: a pin lands on the village AND its unplaced stations, never on a
station that already knows better; clearing forgets everywhere; and a
mis-tap outside the region fails while the operator can still see which
village they were holding.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def unplaced_village(client: TestClient, admin_session: dict) -> dict:
    """A village with stations and no coordinates -- manufactured.

    The e2e seed places everything it creates, so the unplaced state the
    tool exists for is produced here with the tool's own clear, and undone
    with the tool's own place: the fixture is itself a round-trip test.
    """
    rows = client.get(
        "/api/v1/admin/villages", params={"limit": 200}, headers=admin_session
    ).json()["data"]
    village = next(v for v in rows if v["station_count"] > 0 and v["latitude"] is not None)
    original = (str(village["latitude"]), str(village["longitude"]))
    cleared = client.patch(
        f"/api/v1/admin/villages/{village['id']}/coordinates",
        json={"latitude": None, "longitude": None},
        headers=admin_session,
    )
    assert cleared.status_code == 200, cleared.text
    village["latitude"] = village["longitude"] = None
    yield village
    # The village leaves exactly as it arrived; re-placing also re-points
    # the stations the clear emptied, with the same values the seed used.
    restored = client.patch(
        f"/api/v1/admin/villages/{village['id']}/coordinates",
        json={"latitude": original[0], "longitude": original[1]},
        headers=admin_session,
    )
    assert restored.status_code == 200, restored.text


class TestPlacing:
    def test_the_pin_lands_on_village_and_its_unplaced_stations(
        self, client: TestClient, admin_session: dict, unplaced_village: dict
    ):
        placed = client.patch(
            f"/api/v1/admin/villages/{unplaced_village['id']}/coordinates",
            json={"latitude": "35.02000", "longitude": "68.83000"},
            headers=admin_session,
        )
        assert placed.status_code == 200, placed.text
        body = placed.json()["data"]
        assert body["latitude"] == 35.02
        assert len(body["stations_updated"]) == unplaced_village["station_count"]

        listed = client.get(
            "/api/v1/admin/villages",
            params={"q": unplaced_village["name"], "limit": 50},
            headers=admin_session,
        ).json()["data"]
        me = next(v for v in listed if v["id"] == unplaced_village["id"])
        assert me["latitude"] == 35.02

    def test_clearing_forgets_everywhere(
        self, client: TestClient, admin_session: dict, unplaced_village: dict
    ):
        url = f"/api/v1/admin/villages/{unplaced_village['id']}/coordinates"
        client.patch(url, json={"latitude": "35.02", "longitude": "68.83"},
                     headers=admin_session)
        cleared = client.patch(
            url, json={"latitude": None, "longitude": None}, headers=admin_session
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["data"]["latitude"] is None
        assert len(cleared.json()["data"]["stations_updated"]) == \
            unplaced_village["station_count"]


class TestRefusals:
    def test_a_pin_in_the_arabian_sea_is_refused(
        self, client: TestClient, admin_session: dict, unplaced_village: dict
    ):
        refused = client.patch(
            f"/api/v1/admin/villages/{unplaced_village['id']}/coordinates",
            json={"latitude": "20.0", "longitude": "63.0"},
            headers=admin_session,
        )
        assert refused.status_code == 422, refused.text

    def test_half_a_coordinate_is_a_typo_not_a_request(
        self, client: TestClient, admin_session: dict, unplaced_village: dict
    ):
        refused = client.patch(
            f"/api/v1/admin/villages/{unplaced_village['id']}/coordinates",
            json={"latitude": "35.0", "longitude": None},
            headers=admin_session,
        )
        assert refused.status_code == 422, refused.text

    def test_a_passenger_cannot_place_anything(
        self, client: TestClient, passenger_session: dict, admin_session: dict,
        unplaced_village: dict,
    ):
        refused = client.patch(
            f"/api/v1/admin/villages/{unplaced_village['id']}/coordinates",
            json={"latitude": "35.0", "longitude": "68.8"},
            headers=passenger_session,
        )
        assert refused.status_code == 403, refused.text


class TestAlreadyPlacedStationsKeepTheirPoint:
    def test_a_station_with_its_own_point_is_not_overwritten(
        self, client: TestClient, admin_session: dict
    ):
        # خیشکی's village row: its station was seeded with real coordinates.
        rows = client.get(
            "/api/v1/admin/villages", params={"q": "خیشکی", "limit": 10},
            headers=admin_session,
        ).json()["data"]
        village = next(v for v in rows if v["name"] == "خیشکی")
        before_lat = village["latitude"]
        moved = client.patch(
            f"/api/v1/admin/villages/{village['id']}/coordinates",
            json={"latitude": "35.20000", "longitude": "68.70000"},
            headers=admin_session,
        )
        assert moved.status_code == 200, moved.text
        # The village moved, but its already-placed station kept its point.
        assert moved.json()["data"]["stations_updated"] == []
        # Put the village back exactly as the seed had it.
        client.patch(
            f"/api/v1/admin/villages/{village['id']}/coordinates",
            json={"latitude": str(before_lat), "longitude": str(village["longitude"])},
            headers=admin_session,
        )


class TestThePageItself:
    def test_the_page_and_its_vendored_assets_arrive(self, client: TestClient):
        page = client.get("/admin/placer")
        assert page.status_code == 200
        assert "نقطه‌گذاری قریه‌ها" in page.text
        assert "/admin/placer/assets/maplibre-gl.js" in page.text
        js = client.get("/admin/placer/assets/maplibre-gl.js")
        assert js.status_code == 200 and len(js.content) > 100_000
        assert client.get("/admin/placer/assets/evil.js").status_code in (404, 422)
