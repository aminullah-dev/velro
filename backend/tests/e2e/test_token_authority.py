"""A token's claims are a cache; the database is the authority.

An access token is signed and self-contained, so it keeps asserting whatever it
said at sign-in until it expires. Trusting that means a revoked role, a
suspended account or a deleted user goes on working for the lifetime of the
token -- fifteen minutes in which someone just suspended can still approve
drivers and change prices.

Each test here fails if `current_actor` goes back to reading roles out of the
token.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

pytestmark = pytest.mark.integration


def _session():
    from ui.api import deps

    return deps._session_factory()()


@pytest.fixture(scope="module")
def admin_headers(admin_session: dict) -> dict:
    return admin_session


def test_a_valid_token_works_normally(client: TestClient, admin_headers: dict) -> None:
    assert client.get("/api/v1/admin/dashboard", headers=admin_headers).status_code == 200


def test_a_token_for_a_deleted_user_is_refused(
    client: TestClient, admin_headers: dict
) -> None:
    """The case a database reseed produced: a signature that still verifies for
    a subject that is no longer there."""
    from infrastructure.db.models.identity import UserRow

    with _session() as session:
        user = session.scalars(
            select(UserRow).where(UserRow.phone == "+93700000001")
        ).one()
        original_deleted_at = user.deleted_at
        user.deleted_at = user.created_at    # soft delete
        session.commit()

    try:
        response = client.get("/api/v1/admin/dashboard", headers=admin_headers)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "USER_NOT_FOUND"
    finally:
        with _session() as session:
            user = session.scalars(
                select(UserRow).where(UserRow.phone == "+93700000001")
            ).one()
            user.deleted_at = original_deleted_at
            session.commit()


def test_a_suspended_account_loses_access_immediately(
    client: TestClient, admin_headers: dict
) -> None:
    """Not when the token expires. Now."""
    from domain.enums import UserStatus
    from infrastructure.db.models.identity import UserRow

    with _session() as session:
        user = session.scalars(
            select(UserRow).where(UserRow.phone == "+93700000001")
        ).one()
        user.status = UserStatus.SUSPENDED.value
        session.commit()

    try:
        response = client.get("/api/v1/admin/dashboard", headers=admin_headers)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "USER_SUSPENDED"
    finally:
        with _session() as session:
            user = session.scalars(
                select(UserRow).where(UserRow.phone == "+93700000001")
            ).one()
            user.status = UserStatus.ACTIVE.value
            session.commit()


def test_revoking_a_role_takes_effect_on_the_next_request(
    client: TestClient, admin_headers: dict
) -> None:
    """The token still says SUPER_ADMIN. The database no longer does.

    This is the case that matters most: the account stays usable, so nothing
    looks wrong, but the privilege it lost must actually be gone.
    """
    from infrastructure.db.models.identity import RoleRow, UserRoleRow, UserRow

    assert client.get("/api/v1/admin/dashboard", headers=admin_headers).status_code == 200

    with _session() as session:
        user = session.scalars(
            select(UserRow).where(UserRow.phone == "+93700000001")
        ).one()
        staff_links = session.scalars(
            select(UserRoleRow)
            .join(RoleRow, RoleRow.id == UserRoleRow.role_id)
            .where(UserRoleRow.user_id == user.id, RoleRow.is_staff.is_(True))
        ).all()
        removed = [link.id for link in staff_links]
        for link in staff_links:
            link.deleted_at = user.created_at
        session.commit()

    try:
        response = client.get("/api/v1/admin/dashboard", headers=admin_headers)
        assert response.status_code == 403, "a revoked role must stop working at once"
        assert response.json()["error"]["code"] == "PERMISSION_DENIED"
    finally:
        with _session() as session:
            for link_id in removed:
                link = session.get(UserRoleRow, link_id)
                if link is not None:
                    link.deleted_at = None
            session.commit()


def test_a_token_signed_with_another_secret_is_refused(client: TestClient) -> None:
    """Belt and braces: the signature check still runs first."""
    from datetime import UTC, datetime, timedelta

    from infrastructure.services.tokens import JwtTokenService

    forged = JwtTokenService("a" * 40).issue_access_token(
        user_id="whoever",
        roles=["SUPER_ADMIN"],
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )
    response = client.get(
        "/api/v1/admin/dashboard", headers={"Authorization": f"Bearer {forged}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_INVALID"


def test_a_brand_new_user_can_sign_in(client: TestClient) -> None:
    """The first request a new person ever makes.

    Creating the user left `status` to the column default, which SQLAlchemy
    applies at flush -- so the sign-in path, which reads it immediately to check
    the account is active, saw None and returned a 500. Every earlier test used
    a seeded user, so nothing caught it.
    """
    from tests.e2e.conftest import sign_in

    session = sign_in(client, "+93700000099")
    assert session["is_new_user"] is True
    assert "PASSENGER" in session["roles"]

    profile = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {session['access_token']}"},
    )
    assert profile.status_code == 200
    assert profile.json()["data"]["status"] == "ACTIVE"


def test_a_number_typed_without_a_prefix_follows_the_configured_country(
    client: TestClient,
) -> None:
    """+93 is a setting, not a constant.

    Ghorband is Afghanistan, and it stays the default. But a hardcoded country
    code is exactly the city-specific constant this product is supposed not to
    contain -- and it is what makes a real handset in another country
    untestable: "3438677631" silently becomes +933438677631, the code goes to
    an account nobody owns, and the failure looks like a broken OTP rather than
    a wrong country.
    """
    from application.use_cases.authenticate import _country

    class Settings:
        def __init__(self, value):
            self.value = value

        def get_str(self, key, default=None):
            return self.value if key == "auth.default_country_code" else default

    assert _country(Settings("93")) == "93"
    assert _country(Settings("1")) == "1"
    assert _country(Settings("+1")) == "1"
    # A malformed value would build an unparseable number for every user at
    # once, so it falls back rather than propagating.
    assert _country(Settings("")) == "93"
    assert _country(Settings("nonsense")) == "93"
    assert _country(Settings("99999")) == "93"


def test_an_afghan_number_is_unchanged_by_the_default(client: TestClient) -> None:
    """The product's own numbers must keep working exactly as before."""
    from domain.identity import PhoneNumber

    assert str(PhoneNumber.parse("0700123456")) == "+93700123456"
    assert str(PhoneNumber.parse("+93700123456")) == "+93700123456"
    # And a fully-qualified foreign number is honoured whatever the default is.
    assert str(PhoneNumber.parse("+1 343 867 7631", default_country_code="93")) == "+13438677631"
