"""Learning what people are called, over the wire.

Every account created by signing in through the app has a null name -- the only
five with one came from the seed. This covers the paths that change that, and
the rules about who may write over whom.

Dedicated phone numbers per test: sharing one trips the OTP rate limiter, which
is the limiter working correctly.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from infrastructure.services.settings import DEFAULTS
from tests.e2e.conftest import auth, sign_in

pytestmark = pytest.mark.integration

JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    + b"\x00" * 128
    + b"\xff\xd9"
)


def name_of(client: TestClient, headers: dict) -> str | None:
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]["full_name"]


class TestSigningIn:
    def test_a_new_person_has_no_name(self, client: TestClient) -> None:
        """The state of every real account in the database today.

        Worth asserting rather than assuming: it is why "—" appeared on the
        offer card, the receipt and the emergency SMS, and it stayed invisible
        because every demo was run against a seeded account that had one.
        """
        headers = auth(sign_in(client, "+93700000811"))
        assert name_of(client, headers) is None


class TestTheirOwnAccount:
    def test_a_person_can_name_themselves(self, client: TestClient) -> None:
        headers = auth(sign_in(client, "+93700000812"))
        response = client.patch(
            "/api/v1/auth/me", headers=headers, json={"full_name": "  محمد نعیم "}
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["full_name"] == "محمد نعیم"
        assert name_of(client, headers) == "محمد نعیم"

    def test_a_person_can_change_their_own_name(self, client: TestClient) -> None:
        headers = auth(sign_in(client, "+93700000813"))
        client.patch("/api/v1/auth/me", headers=headers, json={"full_name": "محمد"})
        client.patch("/api/v1/auth/me", headers=headers, json={"full_name": "محمد نعیم"})
        assert name_of(client, headers) == "محمد نعیم"

    def test_a_person_can_take_their_name_back(self, client: TestClient) -> None:
        """A handset gets handed on, and the name on it should be able to leave.

        Before this an empty string was stored verbatim, which is neither a
        name nor an absence: every fallback in the product checks for null, so
        "" rendered as a blank that no code path knew was blank.
        """
        headers = auth(sign_in(client, "+93700000814"))
        client.patch("/api/v1/auth/me", headers=headers, json={"full_name": "زرغونه"})
        response = client.patch("/api/v1/auth/me", headers=headers, json={"full_name": ""})
        assert response.status_code == 200, response.text
        assert name_of(client, headers) is None

    def test_a_single_letter_is_not_stored(self, client: TestClient) -> None:
        """Typed to get past the field, not to answer it.

        Storing it would defeat every fallback at once -- the driver's number
        in the emergency SMS keys on the name being absent, and "G" is not
        absent. It is not an error either: the request succeeds and the name
        stays unset.
        """
        headers = auth(sign_in(client, "+93700000815"))
        response = client.patch("/api/v1/auth/me", headers=headers, json={"full_name": "G"})
        assert response.status_code == 200, response.text
        assert name_of(client, headers) is None

    def test_an_over_long_name_is_refused_rather_than_truncated(
        self, client: TestClient
    ) -> None:
        headers = auth(sign_in(client, "+93700000816"))
        response = client.patch(
            "/api/v1/auth/me", headers=headers, json={"full_name": "م" * 161}
        )
        assert response.status_code == 422
        assert name_of(client, headers) is None


class TestApplyingToDrive:
    def test_the_apply_form_records_the_name(self, client: TestClient) -> None:
        headers = auth(sign_in(client, "+93700000817"))
        response = client.post(
            "/api/v1/driver/register", headers=headers, json={"full_name": "گل احمد"}
        )
        assert response.status_code == 200, response.text
        assert name_of(client, headers) == "گل احمد"

    def test_applying_without_a_name_is_fine(self, client: TestClient) -> None:
        """The field is optional, and a man who cannot write must still be able
        to apply. An operator fills it at approval from the tazkira."""
        headers = auth(sign_in(client, "+93700000818"))
        assert (
            client.post("/api/v1/driver/register", headers=headers, json={}).status_code
            == 200
        )
        assert name_of(client, headers) is None


# Read from the settings, not restated: what an operator configured is what
# approval demands, and a list copied into a test is a list that goes stale.
REQUIRED = tuple(DEFAULTS["driver.required_documents"])


def approve(
    client: TestClient, admin: dict, applicant: dict, driver_id: str, **body
) -> None:
    """Everything approval needs, then the approval itself."""
    for kind in REQUIRED:
        uploaded = client.post(
            "/api/v1/driver/documents",
            headers=applicant,
            files={"file": (f"{kind.lower()}.jpg", JPEG, "image/jpeg")},
            data={"document_type_code": kind},
        )
        assert uploaded.status_code in (200, 201), uploaded.text
        document_id = uploaded.json()["data"]["id"]
        reviewed = client.post(
            f"/api/v1/admin/documents/{document_id}/review",
            headers=admin,
            json={"verified": True, "expires_on": "2030-01-01"},
        )
        assert reviewed.status_code == 200, reviewed.text
    response = client.post(
        f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin, json=body
    )
    assert response.status_code == 200, response.text


class TestTheOperatorsName:
    """The best name VELRO gets, and the only place a wrong one can be fixed."""

    def test_an_operator_fills_a_blank_name_from_the_tazkira(
        self, client: TestClient, admin_session: dict
    ) -> None:
        applicant = auth(sign_in(client, "+93700000819"))
        registered = client.post("/api/v1/driver/register", headers=applicant, json={})
        driver_id = registered.json()["data"]["driver_id"]

        approve(client, admin_session, applicant, driver_id, full_name="گل احمد نیازی")
        assert name_of(client, applicant) == "گل احمد نیازی"

    def test_an_operator_may_correct_a_name_the_applicant_gave(
        self, client: TestClient, admin_session: dict
    ) -> None:
        """The repair path.

        The apply form appears on whatever handset a household shares, so the
        name it collects may be a brother's, or a nickname. The operator has
        the document in front of them, and passengers read this name before
        getting into his car.
        """
        applicant = auth(sign_in(client, "+93700000820"))
        registered = client.post(
            "/api/v1/driver/register", headers=applicant, json={"full_name": "گلی"}
        )
        driver_id = registered.json()["data"]["driver_id"]
        assert name_of(client, applicant) == "گلی"

        approve(client, admin_session, applicant, driver_id, full_name="گل احمد نیازی")
        assert name_of(client, applicant) == "گل احمد نیازی"

    def test_approving_without_a_name_leaves_the_one_he_gave(
        self, client: TestClient, admin_session: dict
    ) -> None:
        """Every field on the approval body is optional, so a caller that posts
        nothing -- the panel before this change, and several tests -- still
        works and does not blank anybody."""
        applicant = auth(sign_in(client, "+93700000821"))
        registered = client.post(
            "/api/v1/driver/register",
            headers=applicant,
            json={"full_name": "گل احمد"},
        )
        driver_id = registered.json()["data"]["driver_id"]

        approve(client, admin_session, applicant, driver_id)
        assert name_of(client, applicant) == "گل احمد"

    def test_naming_someone_is_audited_against_the_operator(
        self, client: TestClient, admin_session: dict
    ) -> None:
        """Not against the person named.

        The audit log's one job is saying which person did this, and an entry
        crediting the driver with his own renaming answers it wrongly.
        """
        applicant = auth(sign_in(client, "+93700000822"))
        registered = client.post("/api/v1/driver/register", headers=applicant, json={})
        driver_id = registered.json()["data"]["driver_id"]
        approve(client, admin_session, applicant, driver_id, full_name="نجیب الله")

        entries = client.get(
            "/api/v1/admin/audit", headers=admin_session, params={"action": "user.name_recorded"}
        )
        assert entries.status_code == 200, entries.text
        rows = entries.json()["data"]
        assert rows, "the naming must be on the record"
        assert rows[0]["actor_role"] == "ADMIN"
        assert rows[0]["after"]["full_name"] == "نجیب الله"
