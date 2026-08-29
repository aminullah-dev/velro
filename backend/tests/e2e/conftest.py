"""End-to-end fixtures.

One fully wired application against its own seeded database, shared by every
module here. Session-scoped: seeding is the slow part, and the tests are written
not to depend on each other's leftovers.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from infrastructure.db.session import build_engine, build_session_factory
from shared import config

DATABASE_URL = os.environ.get(
    "VELRO_TEST_DATABASE_URL", "postgresql+psycopg://localhost/velro_e2e"
)


@pytest.fixture(scope="session")
def client():
    """A fully wired application against its own seeded database."""
    os.environ["VELRO_DATABASE_URL"] = DATABASE_URL
    os.environ.setdefault("VELRO_JWT_SECRET", "test-secret-key-at-least-32-characters")
    os.environ["VELRO_OTP_DEBUG_ECHO"] = "true"

    import infrastructure.db.models  # noqa: F401
    from infrastructure.db.base import Base
    from scripts.seed import seed
    from ui.api import deps

    # The composition root caches settings and the engine; clear them so this
    # module's database is the one that gets used.
    deps.settings.cache_clear()
    deps._engine.cache_clear()
    deps._session_factory.cache_clear()
    deps.tokens.cache_clear()

    engine = build_engine(DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with build_session_factory(engine)() as session:
        seed(session)

    from ui.api.app import create_app

    with TestClient(create_app(config.load()), raise_server_exceptions=False) as c:
        yield c




def sign_in(client: TestClient, phone: str) -> dict:
    """Phone + OTP, exactly as a handset does it."""
    requested = client.post(
        "/api/v1/auth/otp/request", json={"phone": phone, "locale": "fa-AF"}
    )
    assert requested.status_code == 200, requested.text
    code = requested.json()["data"]["debug_code"]
    assert code, "development build must echo the code"

    verified = client.post(
        "/api/v1/auth/otp/verify",
        json={"phone": phone, "code": code, "device_id": "test-device", "locale": "fa-AF"},
    )
    assert verified.status_code == 200, verified.text
    return verified.json()["data"]


def auth(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['access_token']}"}


# One sign-in per persona for the whole run. Signing in per module trips the
# OTP rate limiter, which is the limiter working correctly -- a real operator
# signs in once and then works.
@pytest.fixture(scope="session")
def admin_session(client: TestClient) -> dict:
    return auth(sign_in(client, "+93700000001"))


@pytest.fixture(scope="session")
def driver_session(client: TestClient) -> dict:
    return auth(sign_in(client, "+93700000020"))


@pytest.fixture(scope="session")
def passenger_session(client: TestClient) -> dict:
    return auth(sign_in(client, "+93700000010"))
