"""Driver documents: upload, review, approval.

Sections 27, 28 and 51. These are photographs of national identity cards, so
the tests cover who can read them as carefully as they cover the workflow.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from infrastructure.services.settings import DEFAULTS
from tests.e2e.conftest import auth, sign_in

pytestmark = pytest.mark.integration

# A real JPEG header, so the content sniffing accepts it.
JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    + b"\x00" * 128
    + b"\xff\xd9"
)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128
# Read from the settings rather than restated here. A copy of the list in a
# test is a copy that goes stale, and what these tests are checking is that the
# API reports whatever an operator configured -- not that the list is any
# particular length. What the list must *contain* is asserted separately.
REQUIRED = tuple(DEFAULTS["driver.required_documents"])


def upload(client: TestClient, headers: dict, kind: str, content: bytes = JPEG,
           content_type: str = "image/jpeg"):
    return client.post(
        "/api/v1/driver/documents",
        headers=headers,
        files={"file": (f"{kind.lower()}.jpg", content, content_type)},
        data={"document_type_code": kind},
    )


@pytest.fixture(scope="module")
def admin(admin_session: dict) -> dict:
    return admin_session


@pytest.fixture(scope="module")
def applicant(client: TestClient, passenger_session: dict) -> dict:
    """A passenger who applies to drive, so this module has its own driver."""
    client.post("/api/v1/driver/register", headers=passenger_session, json={})
    return passenger_session


class TestUpload:
    def test_a_new_applicant_starts_with_everything_missing(
        self, client: TestClient, applicant: dict
    ) -> None:
        body = client.get("/api/v1/driver/documents", headers=applicant).json()["data"]
        assert sorted(body["required"]) == sorted(REQUIRED)
        assert sorted(body["missing"]) == sorted(REQUIRED)
        assert body["can_work"] is False

    def test_uploading_stores_a_pending_document(
        self, client: TestClient, applicant: dict
    ) -> None:
        response = upload(client, applicant, "LICENSE")
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == "PENDING"

    def test_the_bytes_decide_the_type_not_the_header(
        self, client: TestClient, applicant: dict
    ) -> None:
        """A script renamed .jpg and sent as image/jpeg is still a script.

        The declared content type is a claim by the client and is not consulted.
        """
        response = upload(
            client, applicant, "LICENSE",
            content=b'<?php system($_GET["c"]); ?>',
            content_type="image/jpeg",
        )
        assert response.status_code == 422
        assert response.json()["error"]["context"]["reason"] == "unsupported_type"

    def test_an_empty_file_is_refused(self, client: TestClient, applicant: dict) -> None:
        response = upload(client, applicant, "LICENSE", content=b"")
        assert response.status_code == 422

    def test_an_unknown_document_type_is_refused(
        self, client: TestClient, applicant: dict
    ) -> None:
        response = upload(client, applicant, "FAVOURITE_POEM")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "DOCUMENT_TYPE_UNKNOWN"

    def test_png_is_accepted_too(self, client: TestClient, applicant: dict) -> None:
        assert upload(client, applicant, "NATIONAL_ID", PNG, "image/png").status_code == 200

    def test_re_uploading_keeps_the_earlier_attempt(
        self, client: TestClient, applicant: dict
    ) -> None:
        """A driver has to be able to see why the first photograph was refused."""
        first = upload(client, applicant, "VEHICLE_REGISTRATION").json()["data"]
        second = upload(client, applicant, "VEHICLE_REGISTRATION").json()["data"]

        assert second["supersedes_id"] == first["id"]
        body = client.get("/api/v1/driver/documents", headers=applicant).json()["data"]
        for kind in ("VEHICLE_REGISTRATION",):
            of_kind = [d for d in body["documents"] if d["document_type_code"] == kind]
            assert len(of_kind) >= 2, "the earlier upload must survive"
            assert sum(1 for d in of_kind if d["is_current"]) == 1


class TestAccess:
    """Who may read a photograph of someone's identity card."""

    def _a_document(self, client: TestClient, applicant: dict) -> str:
        upload(client, applicant, "LICENSE")
        body = client.get("/api/v1/driver/documents", headers=applicant).json()["data"]
        return body["documents"][0]["id"]

    def test_the_owner_can_read_their_own(
        self, client: TestClient, applicant: dict
    ) -> None:
        document_id = self._a_document(client, applicant)
        response = client.get(
            f"/api/v1/driver/documents/{document_id}/file", headers=applicant
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"

    def test_another_driver_cannot(
        self, client: TestClient, applicant: dict, driver_session: dict
    ) -> None:
        document_id = self._a_document(client, applicant)
        other = driver_session
        response = client.get(
            f"/api/v1/driver/documents/{document_id}/file", headers=other
        )
        # Not 403: the same answer as "no such document", so the endpoint cannot
        # be used to discover which document ids exist.
        assert response.status_code == 404

    def test_anonymous_cannot(self, client: TestClient, applicant: dict) -> None:
        document_id = self._a_document(client, applicant)
        assert client.get(f"/api/v1/driver/documents/{document_id}/file").status_code == 401
        assert client.get(f"/api/v1/admin/documents/{document_id}/file").status_code == 401

    def test_a_driver_cannot_use_the_staff_route(
        self, client: TestClient, applicant: dict
    ) -> None:
        document_id = self._a_document(client, applicant)
        response = client.get(
            f"/api/v1/admin/documents/{document_id}/file", headers=applicant
        )
        assert response.status_code == 403

    def test_staff_can_read_it(
        self, client: TestClient, applicant: dict, admin: dict
    ) -> None:
        document_id = self._a_document(client, applicant)
        assert client.get(
            f"/api/v1/admin/documents/{document_id}/file", headers=admin
        ).status_code == 200

    def test_the_response_is_not_cacheable(
        self, client: TestClient, applicant: dict, admin: dict
    ) -> None:
        """A shared proxy or a browser cache holding an identity card is a leak
        that outlives the request."""
        document_id = self._a_document(client, applicant)
        response = client.get(
            f"/api/v1/admin/documents/{document_id}/file", headers=admin
        )
        assert "no-store" in response.headers["cache-control"]
        assert response.headers["x-content-type-options"] == "nosniff"


class TestReview:
    def _current(self, client: TestClient, admin: dict, driver_id: str) -> list[dict]:
        body = client.get(
            f"/api/v1/admin/drivers/{driver_id}/documents", headers=admin
        ).json()["data"]
        return [d for d in body["documents"] if d["is_current"]]

    def _driver_id(self, client: TestClient, admin: dict) -> str:
        drivers = client.get("/api/v1/admin/drivers", headers=admin).json()["data"]
        return next(d["id"] for d in drivers if d["approval_status"] == "PENDING")

    def test_rejecting_requires_a_reason(
        self, client: TestClient, applicant: dict, admin: dict
    ) -> None:
        """A driver told only "rejected" has to guess what to photograph again."""
        upload(client, applicant, "LICENSE")
        driver_id = self._driver_id(client, admin)
        document = self._current(client, admin, driver_id)[0]

        response = client.post(
            f"/api/v1/admin/documents/{document['id']}/review",
            headers=admin, json={"verified": False},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "DOCUMENT_REJECTION_REASON_REQUIRED"

    def test_a_rejection_reason_reaches_the_driver(
        self, client: TestClient, applicant: dict, admin: dict
    ) -> None:
        upload(client, applicant, "LICENSE")
        driver_id = self._driver_id(client, admin)
        document = next(
            d for d in self._current(client, admin, driver_id)
            if d["document_type_code"] == "LICENSE"
        )

        client.post(
            f"/api/v1/admin/documents/{document['id']}/review",
            headers=admin,
            json={"verified": False, "rejection_reason": "عکس واضح نیست"},
        )
        body = client.get("/api/v1/driver/documents", headers=applicant).json()["data"]
        rejected = next(
            d for d in body["documents"]
            if d["id"] == document["id"]
        )
        assert rejected["status"] == "REJECTED"
        assert rejected["rejection_reason"] == "عکس واضح نیست"

    def test_a_driver_cannot_be_approved_until_every_document_is_verified(
        self, client: TestClient, applicant: dict, admin: dict
    ) -> None:
        """Section 28. The gate is in the domain entity, so no request shape
        can get past it."""
        driver_id = self._driver_id(client, admin)

        response = client.post(
            f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin
        )
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "DRIVER_DOCUMENTS_INCOMPLETE"
        assert response.json()["error"]["context"]["missing"]

    def test_verifying_all_of_them_allows_approval(
        self, client: TestClient, applicant: dict, admin: dict
    ) -> None:
        for kind in REQUIRED:
            upload(client, applicant, kind)
        driver_id = self._driver_id(client, admin)

        for document in self._current(client, admin, driver_id):
            client.post(
                f"/api/v1/admin/documents/{document['id']}/review",
                headers=admin, json={"verified": True, "expires_on": "2030-01-01"},
            )

        response = client.post(
            f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["approval_status"] == "APPROVED"

    def test_replacing_a_document_returns_an_approved_driver_to_pending(
        self, client: TestClient, applicant: dict, admin: dict
    ) -> None:
        """The approval was for the documents that were reviewed, not for the
        driver in perpetuity."""
        before = client.get("/api/v1/driver/documents", headers=applicant).json()["data"]
        assert before["approval_status"] == "APPROVED"

        upload(client, applicant, "LICENSE")

        after = client.get("/api/v1/driver/documents", headers=applicant).json()["data"]
        assert after["approval_status"] == "PENDING"
        assert after["can_work"] is False

    def test_the_whole_flow_is_audited(
        self, client: TestClient, admin: dict
    ) -> None:
        entries = client.get("/api/v1/admin/audit?limit=200", headers=admin).json()["data"]
        actions = {e["action"] for e in entries}
        assert "driver.registered" in actions
        assert "driver.document_uploaded" in actions
        assert "driver.document_reviewed" in actions
        assert "driver.approved" in actions

        # The key that retrieves an identity document must never be in an audit
        # diff -- the trail is exported and read by support staff.
        for entry in entries:
            for payload in (entry.get("before") or {}, entry.get("after") or {}):
                assert "file_key" not in payload


class TestRegistration:
    def test_registering_twice_is_refused(
        self, client: TestClient, applicant: dict
    ) -> None:
        response = client.post("/api/v1/driver/register", headers=applicant, json={})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "DRIVER_ALREADY_REGISTERED"

    def test_a_signed_out_visitor_cannot_register(self, client: TestClient) -> None:
        assert client.post("/api/v1/driver/register", json={}).status_code == 401


# -- who the driver actually is ------------------------------------------

def test_a_driver_is_not_approved_on_a_tazkira_alone(client: TestClient) -> None:
    """A tazkira proves a document exists, not that its holder is here.

    A passenger getting into a stranger's car is trusting that VELRO checked the
    face against the document, so the photo is required rather than nice to
    have -- a borrowed or stolen tazkira defeats the whole check without it.
    """
    session = auth(sign_in(client, "+93700000140"))
    client.post("/api/v1/driver/register", json={}, headers=session)

    checklist = client.get("/api/v1/driver/documents", headers=session).json()["data"]
    assert "SELFIE" in checklist["required"], "a face is part of proving who this is"
    assert "SELFIE" in checklist["missing"]


def test_verifying_everything_but_the_photo_still_will_not_approve(
    client: TestClient, admin_session: dict
) -> None:
    """The papers can all be in order and the person still unproven."""
    session = auth(sign_in(client, "+93700000141"))
    client.post("/api/v1/driver/register", json={}, headers=session)
    driver_id = client.get("/api/v1/driver/me", headers=session).json()["data"]["id"]

    for code in ("LICENSE", "NATIONAL_ID", "VEHICLE_REGISTRATION"):
        uploaded = upload(client, session, code)
        assert uploaded.status_code in (200, 201), uploaded.text
        client.post(
            f"/api/v1/admin/documents/{uploaded.json()['data']['id']}/review",
            json={"verified": True}, headers=admin_session,
        )

    checklist = client.get("/api/v1/driver/documents", headers=session).json()["data"]
    assert checklist["missing"] == ["SELFIE"], "a face is still owed"
    assert checklist["can_work"] is False

    refused = client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", json={}, headers=admin_session
    )
    assert refused.status_code == 409, "approval without a verified face"


def test_the_verified_photo_completes_the_checklist(
    client: TestClient, admin_session: dict
) -> None:
    session = auth(sign_in(client, "+93700000142"))
    client.post("/api/v1/driver/register", json={}, headers=session)
    for code in ("LICENSE", "NATIONAL_ID", "VEHICLE_REGISTRATION", "SELFIE"):
        uploaded = upload(client, session, code)
        client.post(
            f"/api/v1/admin/documents/{uploaded.json()['data']['id']}/review",
            json={"verified": True}, headers=admin_session,
        )
    checklist = client.get("/api/v1/driver/documents", headers=session).json()["data"]
    assert checklist["missing"] == []
