"""جواز سیر belongs to the car, not the driver.

The defect this replaces: VEHICLE_REGISTRATION was a driver document, so a
driver with one slot for it could register a second car and the first car's
permit stood in for both. These tests are the reason the document moved.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import (
    JPEG,
    approve_driver,
    auth,
    sign_in,
    verify_driver_documents,
    verify_vehicle_documents,
)

pytestmark = pytest.mark.integration


def _driver(client: TestClient, admin_session: dict, phone: str) -> dict:
    session = auth(sign_in(client, phone))
    client.post("/api/v1/driver/register", json={}, headers=session)
    verify_driver_documents(client, session, admin_session)
    approve_driver(client, admin_session, phone)
    return session


def _register(client: TestClient, session: dict, plate: str) -> str:
    created = client.post(
        "/api/v1/driver/vehicle", headers=session,
        json={"vehicle_type_code": "SEDAN", "plate_number": plate},
    )
    assert created.status_code == 200, created.text
    return created.json()["data"]["id"]


def _upload(client: TestClient, session: dict, vehicle_id: str, code: str = "VEHICLE_REGISTRATION"):
    return client.post(
        f"/api/v1/driver/vehicles/{vehicle_id}/documents",
        headers=session,
        files={"file": (f"{code.lower()}.jpg", JPEG, "image/jpeg")},
        data={"document_type_code": code},
    )


def test_one_cars_permit_does_not_certify_another(
    client: TestClient, admin_session: dict
) -> None:
    """The defect, stated as a test.

    While جواز سیر was a driver document there was one slot for it, so a driver
    who had it verified could register a second car and that car inherited a
    permit issued for a different vehicle. Now each car is asked separately.
    """
    session = _driver(client, admin_session, "+93700000160")

    first = _register(client, session, "PRW-1601")
    verify_vehicle_documents(client, session, admin_session, first)
    activated = client.post(
        f"/api/v1/admin/vehicles/{first}/decide",
        json={"approve": True}, headers=admin_session,
    )
    assert activated.status_code == 200, activated.text

    second = _register(client, session, "PRW-1602")
    papers = client.get(
        f"/api/v1/driver/vehicles/{second}/documents", headers=session
    ).json()["data"]
    assert papers["missing"] == ["VEHICLE_REGISTRATION"], (
        "the second car inherited the first car's permit"
    )

    refused = client.post(
        f"/api/v1/admin/vehicles/{second}/decide",
        json={"approve": True}, headers=admin_session,
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "VEHICLE_DOCUMENTS_INCOMPLETE"


def test_each_car_keeps_its_own_papers(
    client: TestClient, admin_session: dict
) -> None:
    """Two cars, two permits, and neither shows up under the other."""
    session = _driver(client, admin_session, "+93700000161")
    first = _register(client, session, "PRW-1611")
    second = _register(client, session, "PRW-1612")

    verify_vehicle_documents(client, session, admin_session, first)
    verify_vehicle_documents(client, session, admin_session, second)

    for vehicle_id, plate in ((first, "PRW-1611"), (second, "PRW-1612")):
        checklist = client.get(
            f"/api/v1/driver/vehicles/{vehicle_id}/documents", headers=session
        ).json()["data"]
        assert checklist["plate_number"] == plate
        assert checklist["missing"] == []
        current = [d for d in checklist["documents"] if d["is_current"]]
        assert len(current) == 1
        assert current[0]["vehicle_id"] == vehicle_id


def test_a_driver_cannot_attach_a_permit_to_someone_elses_car(
    client: TestClient, admin_session: dict
) -> None:
    """Ownership is checked, not taken from the path.

    The permit is what an administrator activates a car on. Without this check
    any signed-in driver could certify a vehicle they have never seen.
    """
    owner = _driver(client, admin_session, "+93700000162")
    stranger = _driver(client, admin_session, "+93700000163")
    theirs = _register(client, owner, "PRW-1621")

    response = _upload(client, stranger, theirs)
    assert response.status_code == 404, response.text
    assert response.json()["error"]["code"] == "VEHICLE_NOT_FOUND"

    reading = client.get(
        f"/api/v1/driver/vehicles/{theirs}/documents", headers=stranger
    )
    assert reading.status_code == 404, reading.text


def test_replacing_a_permit_takes_the_car_out_of_service(
    client: TestClient, admin_session: dict
) -> None:
    """The activation was for the papers that were reviewed.

    Same rule as a driver replacing a document: a new permit nobody has looked
    at must not keep the car on the road on the strength of the old one.
    """
    session = _driver(client, admin_session, "+93700000164")
    vehicle_id = _register(client, session, "PRW-1641")
    verify_vehicle_documents(client, session, admin_session, vehicle_id)
    client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/decide",
        json={"approve": True}, headers=admin_session,
    )

    replaced = _upload(client, session, vehicle_id)
    assert replaced.status_code == 200, replaced.text

    checklist = client.get(
        f"/api/v1/driver/vehicles/{vehicle_id}/documents", headers=session
    ).json()["data"]
    assert checklist["vehicle_status"] == "PENDING"
    assert checklist["can_carry"] is False


def test_a_permit_type_the_platform_does_not_ask_for_is_refused(
    client: TestClient, admin_session: dict
) -> None:
    session = _driver(client, admin_session, "+93700000165")
    vehicle_id = _register(client, session, "PRW-1651")

    response = _upload(client, session, vehicle_id, code="LICENSE")
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "DOCUMENT_TYPE_UNKNOWN"


def test_a_passenger_cannot_read_a_vehicles_papers(
    client: TestClient, admin_session: dict, passenger_session: dict
) -> None:
    session = _driver(client, admin_session, "+93700000166")
    vehicle_id = _register(client, session, "PRW-1661")
    verify_vehicle_documents(client, session, admin_session, vehicle_id)

    document = client.get(
        f"/api/v1/driver/vehicles/{vehicle_id}/documents", headers=session
    ).json()["data"]["documents"][0]

    for headers in (passenger_session, {}):
        response = client.get(
            f"/api/v1/admin/vehicle-documents/{document['id']}/file", headers=headers
        )
        assert response.status_code in (401, 403), response.text
