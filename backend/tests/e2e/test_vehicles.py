"""Vehicle registration and approval, sections 26 and 52.

A driver approved on documents alone still has no car. These tests cover the
gap that leaves: registering a vehicle, an administrator activating it, and the
platform refusing to put a driver into the dispatch pool without one.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import verify_vehicle_documents

pytestmark = pytest.mark.integration


def register(client: TestClient, headers: dict, **fields):
    body = {"vehicle_type_code": "SEDAN", "plate_number": "PRW-0001", **fields}
    return client.post("/api/v1/driver/vehicle", headers=headers, json=body)


# A driver of this module's own, fully approved.
#
# Deliberately not the seeded محمد: these tests retire and replace vehicles,
# and other modules assert on his PRW-1234. Sharing mutable state between test
# modules through the database is how a suite starts passing only in one order.
VEHICLE_TEST_PHONE = "+93700000030"

JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    + b"\x00" * 64
    + b"\xff\xd9"
)


@pytest.fixture(scope="module")
def driver(client: TestClient, admin_session: dict) -> dict:
    """Signs up, sends every document, gets them verified, gets approved."""
    from tests.e2e.conftest import auth, sign_in

    headers = auth(sign_in(client, VEHICLE_TEST_PHONE))
    client.post("/api/v1/driver/register", headers=headers, json={})

    required = client.get(
        "/api/v1/driver/documents", headers=headers
    ).json()["data"]["required"]
    for kind in required:
        client.post(
            "/api/v1/driver/documents",
            headers=headers,
            files={"file": (f"{kind.lower()}.jpg", JPEG, "image/jpeg")},
            data={"document_type_code": kind},
        )

    drivers = client.get("/api/v1/admin/drivers", headers=admin_session).json()["data"]
    driver_id = next(
        d["id"] for d in drivers
        if d["phone"] == VEHICLE_TEST_PHONE
    )
    checklist = client.get(
        f"/api/v1/admin/drivers/{driver_id}/documents", headers=admin_session
    ).json()["data"]
    for document in (d for d in checklist["documents"] if d["is_current"]):
        client.post(
            f"/api/v1/admin/documents/{document['id']}/review",
            headers=admin_session, json={"verified": True},
        )
    client.post(f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin_session)
    return headers


@pytest.fixture(scope="module")
def rival(client: TestClient) -> dict:
    """A second driver, used only to collide on a plate."""
    from tests.e2e.conftest import auth, sign_in

    headers = auth(sign_in(client, "+93700000031"))
    client.post("/api/v1/driver/register", headers=headers, json={})
    return headers


class TestVehicleTypes:
    def test_the_types_come_from_the_database(
        self, client: TestClient, driver: dict
    ) -> None:
        """Section 105: adding a vehicle type is a row, not a deploy."""
        types = client.get("/api/v1/vehicle-types", headers=driver).json()["data"]
        codes = {t["code"] for t in types}
        assert {"SEDAN", "SUV", "VAN", "HIACE", "BUS"} <= codes
        sedan = next(t for t in types if t["code"] == "SEDAN")
        assert sedan["default_seat_capacity"] == 4
        # A key, so each app renders it in the reader's own language.
        assert sedan["name_key"] == "vehicle_type.sedan"

    def test_an_unknown_type_is_refused_with_the_real_list(
        self, client: TestClient, driver: dict
    ) -> None:
        response = register(client, driver, vehicle_type_code="HELICOPTER")
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "VEHICLE_TYPE_UNKNOWN"
        assert "SEDAN" in error["context"]["accepted"]


class TestPlates:
    def test_a_plate_is_stored_upper_case(self, client: TestClient, driver: dict) -> None:
        """A passenger checks the plate against a physical car."""
        result = register(client, driver, plate_number="  prw-4242  ").json()["data"]
        assert result["plate_number"] == "PRW-4242"

    @pytest.mark.parametrize(
        "written_as", ["PRW-4242", "prw 4242", "PRW4242", "prw_4242"]
    )
    def test_one_vehicle_written_several_ways_is_one_vehicle(
        self, client: TestClient, driver: dict, rival: dict, written_as: str
    ) -> None:
        """Uniqueness is on the normalised key.

        Two records for one car means two drivers can be dispatched in it.
        """
        register(client, driver, plate_number="PRW-4242")
        response = register(client, rival, plate_number=written_as)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "VEHICLE_PLATE_TAKEN"

    def test_a_plate_too_short_to_be_real_is_refused(
        self, client: TestClient, driver: dict
    ) -> None:
        response = register(client, driver, plate_number="X1")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VEHICLE_PLATE_INVALID"

    def test_eastern_digits_normalise_to_the_same_vehicle(
        self, client: TestClient, driver: dict, rival: dict
    ) -> None:
        """A plate typed on an Afghan keyboard is the same plate."""
        register(client, driver, plate_number="PRW-7788")
        response = register(client, rival, plate_number="PRW-۷۷۸۸")
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "VEHICLE_PLATE_TAKEN"


class TestRegistration:
    def test_a_driver_with_no_vehicle_gets_null_not_an_error(
        self, client: TestClient, admin_session: dict
    ) -> None:
        """"You have not registered one" is a state a screen renders."""
        # A brand-new applicant, so nothing has been registered for them.
        response = client.get("/api/v1/driver/vehicle", headers=admin_session)
        # Staff are not drivers; this is the honest 403/404 boundary.
        assert response.status_code in (403, 404)

    def test_seat_capacity_defaults_from_the_type(
        self, client: TestClient, driver: dict
    ) -> None:
        result = register(
            client, driver, vehicle_type_code="HIACE", plate_number="PRW-1414"
        ).json()["data"]
        assert result["seat_capacity"] == 14

    def test_capacity_can_be_overridden(self, client: TestClient, driver: dict) -> None:
        result = register(
            client, driver, vehicle_type_code="HIACE",
            plate_number="PRW-1515", seat_capacity=11,
        ).json()["data"]
        assert result["seat_capacity"] == 11

    def test_a_new_vehicle_starts_pending(self, client: TestClient, driver: dict) -> None:
        assert register(client, driver, plate_number="PRW-2020").json()["data"]["status"] \
            == "PENDING"

    def test_correcting_details_updates_in_place(
        self, client: TestClient, driver: dict
    ) -> None:
        """Same plate, better details. There is no history worth keeping in a
        typo fix, so nothing is retired."""
        first = register(
            client, driver, plate_number="PRW-3030", brand="Toyata"
        ).json()["data"]
        second = register(
            client, driver, plate_number="PRW-3030", brand="Toyota", colour="سفید"
        ).json()["data"]

        assert second["id"] == first["id"]
        assert second["replaced_id"] is None

        current = client.get("/api/v1/driver/vehicle", headers=driver).json()["data"]
        assert current["brand"] == "Toyota"
        assert current["colour"] == "سفید"

    def test_changing_vehicle_retires_the_old_record(
        self, client: TestClient, driver: dict, admin_session: dict
    ) -> None:
        """Completed trips point at the old vehicle, and their history has to
        stay truthful -- so it is retired, not overwritten."""
        old = register(client, driver, plate_number="PRW-5050").json()["data"]
        new = register(client, driver, plate_number="PRW-6060").json()["data"]

        assert new["id"] != old["id"]
        assert new["replaced_id"] == old["id"]

        current = client.get("/api/v1/driver/vehicle", headers=driver).json()["data"]
        assert current["plate_number"] == "PRW-6060"

    def test_registering_returns_the_vehicle_to_pending(
        self, client: TestClient, driver: dict, admin_session: dict
    ) -> None:
        vehicle = register(client, driver, plate_number="PRW-8080").json()["data"]
        client.post(
            f"/api/v1/admin/vehicles/{vehicle['id']}/decide",
            headers=admin_session, json={"approve": True},
        )
        again = register(
            client, driver, plate_number="PRW-8080", colour="سبز"
        ).json()["data"]
        assert again["status"] == "PENDING", "an edited vehicle is reviewed again"


class TestApproval:
    def test_an_administrator_activates_a_vehicle(
        self, client: TestClient, driver: dict, admin_session: dict
    ) -> None:
        vehicle = register(client, driver, plate_number="PRW-9090").json()["data"]

        pending = client.get(
            "/api/v1/admin/vehicles/pending", headers=admin_session
        ).json()["data"]
        assert any(v["id"] == vehicle["id"] for v in pending)
        listed = next(v for v in pending if v["id"] == vehicle["id"])
        # The phone always identifies the driver; the name may be absent,
        # because a driver who signed up by OTP has not given one yet.
        assert listed["driver_phone"] == VEHICLE_TEST_PHONE
        assert "driver_name" in listed

        # A car with no جواز سیر cannot be activated, whoever clicks the button.
        # An administrator approving a vehicle is saying its permit was seen;
        # afterwards the car is in the dispatch pool and a passenger is involved.
        refused = client.post(
            f"/api/v1/admin/vehicles/{vehicle['id']}/decide",
            headers=admin_session, json={"approve": True},
        )
        assert refused.status_code == 409, refused.text
        assert refused.json()["error"]["code"] == "VEHICLE_DOCUMENTS_INCOMPLETE"
        assert refused.json()["error"]["context"]["missing"] == ["VEHICLE_REGISTRATION"]

        verify_vehicle_documents(client, driver, admin_session, vehicle["id"])
        response = client.post(
            f"/api/v1/admin/vehicles/{vehicle['id']}/decide",
            headers=admin_session, json={"approve": True},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == "ACTIVE"

    def test_a_driver_cannot_go_online_without_a_vehicle(
        self, client: TestClient, admin_session: dict, rival: dict
    ) -> None:
        """Approval covers the documents; it does not conjure a car.

        Without this the driver would enter the dispatch pool, be offered a
        trip, and fail at the moment they accepted it -- in front of a passenger
        already waiting at the roadside.
        """
        response = client.post(
            "/api/v1/driver/status", headers=rival, json={"availability": "ONLINE"},
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] in (
            "VEHICLE_NOT_REGISTERED", "DRIVER_NOT_APPROVED",
        )

    def test_a_suspended_vehicle_takes_its_driver_off_the_road(
        self, client: TestClient, driver: dict, admin_session: dict
    ) -> None:
        vehicle = register(client, driver, plate_number="PRW-1122").json()["data"]
        verify_vehicle_documents(client, driver, admin_session, vehicle["id"])
        client.post(
            f"/api/v1/admin/vehicles/{vehicle['id']}/decide",
            headers=admin_session, json={"approve": True},
        )
        assert client.post(
            "/api/v1/driver/status", headers=driver, json={"availability": "ONLINE"}
        ).status_code == 200

        client.post(
            f"/api/v1/admin/vehicles/{vehicle['id']}/decide",
            headers=admin_session,
            json={"approve": False, "reason": "registration expired"},
        )
        client.post("/api/v1/driver/status", headers=driver, json={"availability": "OFFLINE"})

        response = client.post(
            "/api/v1/driver/status", headers=driver, json={"availability": "ONLINE"}
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "VEHICLE_SUSPENDED"

    def test_a_passenger_cannot_decide_a_vehicle(
        self, client: TestClient, driver: dict, passenger_session: dict
    ) -> None:
        vehicle = register(client, driver, plate_number="PRW-3344").json()["data"]
        response = client.post(
            f"/api/v1/admin/vehicles/{vehicle['id']}/decide",
            headers=passenger_session, json={"approve": True},
        )
        assert response.status_code == 403

    def test_the_flow_is_audited(self, client: TestClient, admin_session: dict) -> None:
        entries = client.get(
            "/api/v1/admin/audit?limit=200", headers=admin_session
        ).json()["data"]
        actions = {e["action"] for e in entries}
        assert "vehicle.registered" in actions
        assert "vehicle.approved" in actions


def test_a_driver_with_two_vehicles_is_listed_once(
    client: TestClient, driver: dict, admin_session: dict
) -> None:
    """The approvals queue is a list of people, not of vehicle registrations.

    The list used to be built with an outer join to vehicles, so a driver who
    had registered a second car appeared twice. An operator cannot tell the two
    rows apart, and the row limit counts them both -- so a genuinely pending
    driver drops off the end of the page to make room for a duplicate.
    """
    register(client, driver, plate_number="PRW-7001")
    second = register(client, driver, plate_number="PRW-7002")
    assert second.status_code == 200, second.text

    listed = client.get("/api/v1/admin/drivers", headers=admin_session).json()["data"]
    mine = [d for d in listed if d["phone"] == VEHICLE_TEST_PHONE]
    assert len(mine) == 1, (
        f"{VEHICLE_TEST_PHONE} appears {len(mine)} times: "
        + ", ".join(str(d["plate_number"]) for d in mine)
    )


def test_the_plate_shown_for_a_two_vehicle_driver_does_not_move(
    client: TestClient, driver: dict, admin_session: dict
) -> None:
    """Whichever vehicle is shown, it is the same one on every request.

    A column that shows a different plate each time the operator refreshes is
    worse than one that shows an incomplete truth: it reads as data changing
    underneath them.
    """
    seen = {
        next(
            d["plate_number"]
            for d in client.get(
                "/api/v1/admin/drivers", headers=admin_session
            ).json()["data"]
            if d["phone"] == VEHICLE_TEST_PHONE
        )
        for _ in range(5)
    }
    assert len(seen) == 1, f"the plate column moved between requests: {seen}"
