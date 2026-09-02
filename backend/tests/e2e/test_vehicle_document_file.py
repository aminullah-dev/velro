"""The driver's own copy of his car's permit.

The papers card on the handset listed جواز سیر by status and showed no picture
of it, so a wrong page or a hand over the permit was only discovered when the
office refused it. The route that serves a driver his own upload already
existed and nothing had asked for it. Before the app starts to, these pin down
who may read it -- the same shape as the driver's own documents, one level
down: the paper belongs to a car, and the car must belong to the caller.
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
)

pytestmark = pytest.mark.integration


def _driver(client: TestClient, admin_session: dict, phone: str) -> dict:
    session = auth(sign_in(client, phone))
    client.post("/api/v1/driver/register", json={}, headers=session)
    verify_driver_documents(client, session, admin_session)
    approve_driver(client, admin_session, phone)
    return session


def _a_permit(client: TestClient, session: dict, plate: str) -> str:
    """Register a car and send its permit: the document id."""
    created = client.post(
        "/api/v1/driver/vehicle", headers=session,
        json={"vehicle_type_code": "SEDAN", "plate_number": plate},
    )
    assert created.status_code == 200, created.text
    vehicle_id = created.json()["data"]["id"]
    uploaded = client.post(
        f"/api/v1/driver/vehicles/{vehicle_id}/documents",
        headers=session,
        files={"file": ("vehicle_registration.jpg", JPEG, "image/jpeg")},
        data={"document_type_code": "VEHICLE_REGISTRATION"},
    )
    assert uploaded.status_code == 200, uploaded.text
    return uploaded.json()["data"]["id"]


@pytest.fixture(scope="module")
def owner(client: TestClient, admin_session: dict) -> dict:
    return _driver(client, admin_session, "+93700000167")


@pytest.fixture(scope="module")
def stranger(client: TestClient, admin_session: dict) -> dict:
    """Another approved driver, with no claim on the owner's car."""
    return _driver(client, admin_session, "+93700000168")


@pytest.fixture(scope="module")
def permit_id(client: TestClient, owner: dict) -> str:
    return _a_permit(client, owner, "PRW-1671")


class TestAccess:
    """Who may read a photograph of a car's permit."""

    def test_the_owner_can_read_their_own(
        self, client: TestClient, owner: dict, permit_id: str
    ) -> None:
        response = client.get(
            f"/api/v1/driver/vehicle-documents/{permit_id}/file", headers=owner
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"] == "image/jpeg"
        assert response.content == JPEG
        # A scan of a legal document must not outlive the request in a
        # shared proxy or a browser cache.
        assert "no-store" in response.headers["cache-control"]

    def test_another_driver_cannot(
        self, client: TestClient, stranger: dict, permit_id: str
    ) -> None:
        response = client.get(
            f"/api/v1/driver/vehicle-documents/{permit_id}/file", headers=stranger
        )
        # Not 403: the same answer as "no such document", so the route cannot
        # be used to discover which permits exist.
        assert response.status_code == 404, response.text

    def test_a_permit_that_does_not_exist_answers_the_same(
        self, client: TestClient, owner: dict
    ) -> None:
        response = client.get(
            "/api/v1/driver/vehicle-documents/no-such-permit/file", headers=owner
        )
        assert response.status_code == 404, response.text

    def test_anonymous_cannot(self, client: TestClient, permit_id: str) -> None:
        response = client.get(f"/api/v1/driver/vehicle-documents/{permit_id}/file")
        assert response.status_code == 401, response.text
