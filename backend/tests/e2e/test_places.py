"""Naming the place you are standing in, through the front door.

The passenger taps "my current location": the server says which district that
is and which station is nearest, the passenger says what the place is called,
and the name is kept -- for the driver of this request at once, for every
passenger nearby once it is known to be a place (ADR 0015).

Proven here against the seed's own Ghorband villages: خیشکی at its seeded
point, قلعه نو south-east of it, صدوار which people also call سبزوار.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.e2e.conftest import (
    DATABASE_URL,
    auth,
    build_engine,
    build_session_factory,
    road_ready_driver,
    sign_in,
)

KHISHKI = {"latitude": "35.1250", "longitude": "68.7700"}
QALA_NAW = {"latitude": "35.1185", "longitude": "68.7905"}   # a few hundred metres off its pin
SADWAR = {"latitude": "35.1312", "longitude": "68.7553"}
HERAT = {"latitude": "34.35", "longitude": "62.20"}


@pytest.fixture(scope="module")
def rider(client: TestClient) -> dict:
    return auth(sign_in(client, "+93700000610"))


@pytest.fixture(scope="module")
def other_rider(client: TestClient) -> dict:
    return auth(sign_in(client, "+93700000612"))


@pytest.fixture(scope="module")
def driver(client: TestClient, admin_session: dict) -> dict:
    session, _ = road_ready_driver(client, admin_session, "+93700000611", "PLC-0611")
    client.post("/api/v1/driver/status", json={"availability": "ONLINE"}, headers=session)
    return session


def _name(client: TestClient, headers: dict, name: str, where: dict, **extra):
    return client.post(
        "/api/v1/geo/places", json={"name": name, **where, **extra}, headers=headers
    )


def _village_id(client: TestClient, name: str) -> str:
    found = client.get("/api/v1/geo/search", params={"q": name}).json()["data"]
    return next(r["id"] for r in found if r["kind"] == "village" and r["name"] == name)


def _nearby_names(client: TestClient, where: dict) -> list[str]:
    rows = client.get("/api/v1/geo/places/nearby", params=where).json()["data"]
    return [r["name"] for r in rows]


# -- where am I ----------------------------------------------------------

class TestResolve:
    def test_standing_in_khishki(self, client: TestClient):
        got = client.get("/api/v1/geo/resolve", params=KHISHKI)
        assert got.status_code == 200, got.text
        data = got.json()["data"]
        assert data["inside"] is True
        assert data["district"]["code"] == "GRB-SYG"
        # A placed station decided it, not a district's guessed centre.
        assert data["district_source"] == "station"
        assert data["stations"], "the nearest station is the whole point"
        # Within walking distance -- the seed's points are guesses a kilometre
        # or so apart, so this is "near", not "on top of".
        assert data["stations"][0]["distance_m"] < 3_000
        distances = [s["distance_m"] for s in data["stations"]]
        assert distances == sorted(distances)

    def test_herat_is_not_somewhere_velro_goes(self, client: TestClient):
        data = client.get("/api/v1/geo/resolve", params=HERAT).json()["data"]
        assert data["inside"] is False
        assert data["district"] is None
        assert data["stations"] == []


# -- naming it -----------------------------------------------------------

class TestNaming:
    def test_a_known_village_is_approved_at_once(self, client: TestClient, rider: dict):
        named = _name(client, rider, "قلعه نو", QALA_NAW)
        assert named.status_code == 201, named.text
        place = named.json()["data"]
        assert place["status"] == "APPROVED"
        assert place["village_id"] == _village_id(client, "قلعه نو")
        assert place["nearest_station_id"]
        assert "قلعه نو" in _nearby_names(client, QALA_NAW)

    def test_an_alias_is_a_known_village_too(self, client: TestClient, rider: dict):
        place = _name(client, rider, "سبزوار", SADWAR).json()["data"]
        assert place["status"] == "APPROVED"
        assert place["village_id"] == _village_id(client, "صدوار")

    def test_a_new_name_waits_and_is_shown_to_nobody_else(
        self, client: TestClient, rider: dict
    ):
        named = _name(client, rider, "چشمه‌سار", KHISHKI)
        assert named.status_code == 201, named.text
        assert named.json()["data"]["status"] == "PENDING"
        assert "چشمه‌سار" not in _nearby_names(client, KHISHKI)
        resolved = client.get("/api/v1/geo/resolve", params=KHISHKI).json()["data"]
        assert "چشمه‌سار" not in [p["name"] for p in resolved["places"]]

    def test_the_same_name_here_is_the_same_place(
        self, client: TestClient, rider: dict, other_rider: dict, admin_session: dict
    ):
        first = _name(client, rider, "باغ‌بالا", KHISHKI).json()["data"]
        again = _name(
            client, other_rider, "باغ بالا",
            {"latitude": "35.1255", "longitude": "68.7705"},
        ).json()["data"]
        assert again["id"] == first["id"]
        queue = client.get(
            "/api/v1/admin/places", params={"status": "PENDING"}, headers=admin_session
        ).json()["data"]
        assert next(p for p in queue if p["id"] == first["id"])["report_count"] == 2

    def test_nobody_is_written_down(self, client: TestClient, rider: dict):
        """ADR 0015: the row says what a place is called, never who said so."""
        from infrastructure.db.models.geography import PlaceRow

        place = _name(client, rider, "پایین‌ده", KHISHKI).json()["data"]
        with build_session_factory(build_engine(DATABASE_URL))() as session:
            row = session.scalars(select(PlaceRow).where(PlaceRow.id == place["id"])).one()
            assert row.created_by is None
            assert row.updated_by is None
            assert not hasattr(row, "user_id")

    @pytest.mark.parametrize(
        ("name", "reason"),
        [("خانه", "personal"), ("خانهٔ کاکا", "personal"), ("0799123456", "digits"),
         ("مسجد", "generic")],
    )
    def test_a_household_is_not_a_place(
        self, client: TestClient, rider: dict, name: str, reason: str
    ):
        refused = _name(client, rider, name, KHISHKI)
        assert refused.status_code == 422, refused.text
        error = refused.json()["error"]
        assert error["code"] == "PLACE_NAME_NOT_ALLOWED"
        assert error["context"]["reason"] == reason

    def test_a_vague_fix_cannot_name_a_spot(self, client: TestClient, rider: dict):
        refused = _name(client, rider, "سرچشمه", KHISHKI, accuracy_m=2500)
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "PLACE_FIX_TOO_COARSE"

    def test_herat_names_nothing(self, client: TestClient, rider: dict):
        # This rider is fence-exempt, like every test persona -- so it is the
        # use case, finding no district anywhere near, that refuses.
        refused = _name(client, rider, "هرات", HERAT)
        assert refused.status_code == 422, refused.text
        assert refused.json()["error"]["code"] == "GEOFENCE_OUTSIDE"

    def test_signed_out_names_nothing(self, client: TestClient):
        assert _name(client, {}, "سرچشمه", KHISHKI).status_code == 401


# -- staff read the queue ------------------------------------------------

class TestModeration:
    def test_approval_puts_it_in_front_of_everyone(
        self, client: TestClient, rider: dict, admin_session: dict
    ):
        place = _name(client, rider, "گذر سفید", KHISHKI).json()["data"]
        decided = client.post(
            f"/api/v1/admin/places/{place['id']}/approve", json={}, headers=admin_session
        )
        assert decided.status_code == 200, decided.text
        assert decided.json()["data"]["status"] == "APPROVED"
        assert "گذر سفید" in _nearby_names(client, KHISHKI)

    def test_approval_may_correct_the_spelling_but_not_the_rule(
        self, client: TestClient, rider: dict, admin_session: dict
    ):
        place = _name(client, rider, "کوتل سبز", KHISHKI).json()["data"]
        refused = client.post(
            f"/api/v1/admin/places/{place['id']}/approve",
            json={"name": "خانهٔ سبز"}, headers=admin_session,
        )
        assert refused.status_code == 422, refused.text
        renamed = client.post(
            f"/api/v1/admin/places/{place['id']}/approve",
            json={"name": "کوتل سبزک"}, headers=admin_session,
        ).json()["data"]
        assert renamed["name"] == "کوتل سبزک"

    def test_a_rejected_name_stays_rejected(
        self, client: TestClient, rider: dict, admin_session: dict
    ):
        place = _name(client, rider, "حاجی گل", KHISHKI).json()["data"]
        rejected = client.post(
            f"/api/v1/admin/places/{place['id']}/reject", headers=admin_session
        )
        assert rejected.status_code == 200, rejected.text
        again = _name(client, rider, "حاجی گل", KHISHKI)
        assert again.status_code == 422, again.text
        assert again.json()["error"]["context"]["reason"] == "rejected"

    def test_a_passenger_cannot_moderate(self, client: TestClient, rider: dict):
        assert client.get("/api/v1/admin/places", headers=rider).status_code == 403


# -- the driver is told ----------------------------------------------------

def _station_at_khishki(client: TestClient) -> str:
    return client.get("/api/v1/geo/resolve", params=KHISHKI).json()["data"]["stations"][0]["id"]


def _destination(client: TestClient, station_id: str) -> str:
    groups = client.get(f"/api/v1/geo/stations/{station_id}/destinations").json()["data"]
    group = groups[0]
    return (group.get("children") or [group])[0]["id"]


def _ask(client: TestClient, headers: dict, **extra):
    station = _station_at_khishki(client)
    return client.post(
        "/api/v1/ride-requests",
        json={
            "origin_station_id": station,
            "destination_id": _destination(client, station),
            "passenger_count": 1,
            "offered_fare_minor": 50_000,
            **KHISHKI,
            **extra,
        },
        headers=headers,
    )


def _cancel(client: TestClient, headers: dict, request_id: str) -> None:
    done = client.post(f"/api/v1/ride-requests/{request_id}/cancel", headers=headers)
    assert done.status_code == 200, done.text


class TestTheDriverIsTold:
    def test_the_board_says_which_village(
        self, client: TestClient, rider: dict, driver: dict
    ):
        # Pending on purpose: the driver of this one request is told at once,
        # the way he would be told by the note; strangers wait for staff.
        place = _name(client, rider, "سنگ‌سفید", KHISHKI).json()["data"]
        assert place["status"] == "PENDING"
        asked = _ask(client, rider, origin_place_id=place["id"])
        assert asked.status_code == 201, asked.text
        request = asked.json()["data"]
        assert request["origin_place_name"] == "سنگ‌سفید"
        try:
            board = client.get("/api/v1/driver/ride-requests", headers=driver).json()["data"]
            row = next(r for r in board if r["id"] == request["id"])
            assert row["origin_place_name"] == "سنگ‌سفید"
            assert row["origin_station_name"]
            mine = client.get("/api/v1/ride-requests", headers=rider).json()["data"]
            own = next(r for r in mine if r["id"] == request["id"])
            assert own["origin_place_id"] == place["id"]
        finally:
            _cancel(client, rider, request["id"])

    def test_a_rejected_place_cannot_be_asked_from(
        self, client: TestClient, rider: dict, admin_session: dict
    ):
        place = _name(client, rider, "تنگی سرخ", KHISHKI).json()["data"]
        client.post(f"/api/v1/admin/places/{place['id']}/reject", headers=admin_session)
        refused = _ask(client, rider, origin_place_id=place["id"])
        assert refused.status_code == 404, refused.text
        assert refused.json()["error"]["code"] == "PLACE_NOT_FOUND"

    def test_an_unknown_place_is_refused(self, client: TestClient, rider: dict):
        refused = _ask(client, rider, origin_place_id="no-such-place")
        assert refused.status_code == 404, refused.text

    def test_without_a_place_nothing_changes(self, client: TestClient, rider: dict):
        asked = _ask(client, rider)
        assert asked.status_code == 201, asked.text
        request = asked.json()["data"]
        assert request["origin_place_id"] is None
        assert request["origin_place_name"] is None
        _cancel(client, rider, request["id"])


# -- typing the first letters -------------------------------------------

class TestSearch:
    """The origin field's type-ahead: a few letters of a known spot bring back
    its whole name and the coordinates that complete the map."""

    def test_the_first_letters_suggest_a_known_place(
        self, client: TestClient, rider: dict
    ):
        # A known village is approved the moment it is named, so it is the kind
        # of name a stranger typing nearby is allowed to be offered.
        _name(client, rider, "قلعه نو", QALA_NAW)
        found = client.get(
            "/api/v1/geo/places/search", params={"q": "قلعه", **QALA_NAW}
        )
        assert found.status_code == 200, found.text
        hit = next(
            (r for r in found.json()["data"] if r["name"] == "قلعه نو"), None
        )
        assert hit is not None, "the approved place did not come back for its prefix"
        # The whole point: the coordinates and the station ride back with it.
        assert hit["nearest_station_id"]
        assert hit["latitude"] and hit["longitude"]
        # A fix was given, so each suggestion carries how far off it is.
        assert hit["distance_m"] is not None

    def test_a_name_awaiting_staff_is_suggested_to_nobody(
        self, client: TestClient, rider: dict
    ):
        made = _name(client, rider, "ریگ روان", KHISHKI)
        assert made.status_code == 201, made.text
        assert made.json()["data"]["status"] == "PENDING"
        names = [
            r["name"]
            for r in client.get(
                "/api/v1/geo/places/search", params={"q": "ریگ", **KHISHKI}
            ).json()["data"]
        ]
        assert "ریگ روان" not in names

    def test_nonsense_matches_nothing_rather_than_everything(
        self, client: TestClient
    ):
        rows = client.get(
            "/api/v1/geo/places/search", params={"q": "زققظضثصث"}
        ).json()["data"]
        assert rows == []
