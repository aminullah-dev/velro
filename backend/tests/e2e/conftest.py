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
    # The whole test fleet is exempt from the geofence, exactly as the
    # tester's own handset will be in production -- the fence is not what
    # these modules are proving, and none of them carries coordinates. The
    # range covers every +9370000xxNN persona so a future test number works
    # without ceremony. One number is deliberately left out: test_geofence
    # signs it in to walk into the fence from both sides.
    os.environ["VELRO_GEOFENCE_EXEMPT_PHONES"] = ",".join(
        [f"+93700000{n:03d}" for n in range(1000) if n != 555]
        + ["+93700123456"]
    )

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


# -- putting a driver on the road ----------------------------------------
#
# Four steps, and every one of them is a real gate: the driver's own papers,
# their approval, the car, and the car's جواز سیر. Written once here because
# a test that skips a step is a test that stops proving the step exists.

JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    + b"\x00" * 128
    + b"\xff\xd9"
)


def verify_driver_documents(
    client: TestClient, session: dict, admin: dict, *, expires_on: str | None = None
) -> None:
    """Send every document the driver owes, and have an operator verify it."""
    from infrastructure.services.settings import DEFAULTS

    for code in DEFAULTS["driver.required_documents"]:
        uploaded = client.post(
            "/api/v1/driver/documents",
            headers=session,
            files={"file": (f"{code.lower()}.jpg", JPEG, "image/jpeg")},
            data={"document_type_code": code},
        )
        assert uploaded.status_code == 200, uploaded.text
        review = client.post(
            f"/api/v1/admin/documents/{uploaded.json()['data']['id']}/review",
            json={"verified": True, "expires_on": expires_on}, headers=admin,
        )
        assert review.status_code == 200, review.text


def verify_vehicle_documents(
    client: TestClient, session: dict, admin: dict, vehicle_id: str,
    *, expires_on: str | None = None,
) -> None:
    """Send the car's own papers -- جواز سیر -- and have them verified.

    Per vehicle, not per driver: a driver with two cars owes two of these, and
    that is the whole reason these documents moved off the driver.
    """
    from infrastructure.services.settings import DEFAULTS

    for code in DEFAULTS["vehicle.required_documents"]:
        uploaded = client.post(
            f"/api/v1/driver/vehicles/{vehicle_id}/documents",
            headers=session,
            files={"file": (f"{code.lower()}.jpg", JPEG, "image/jpeg")},
            data={"document_type_code": code},
        )
        assert uploaded.status_code == 200, uploaded.text
        review = client.post(
            f"/api/v1/admin/vehicle-documents/{uploaded.json()['data']['id']}/review",
            json={"verified": True, "expires_on": expires_on}, headers=admin,
        )
        assert review.status_code == 200, review.text


def approve_driver(client: TestClient, admin: dict, phone: str) -> str:
    listed = client.get("/api/v1/admin/drivers", headers=admin).json()["data"]
    driver_id = next(d["id"] for d in listed if d["phone"] == phone)
    approved = client.post(f"/api/v1/admin/drivers/{driver_id}/approve", headers=admin)
    assert approved.status_code == 200, approved.text
    return driver_id


def register_and_activate_vehicle(
    client: TestClient, session: dict, admin: dict, plate: str, **fields
) -> str:
    created = client.post(
        "/api/v1/driver/vehicle", headers=session,
        json={"vehicle_type_code": "SEDAN", "plate_number": plate, **fields},
    )
    assert created.status_code == 200, created.text
    vehicle_id = created.json()["data"]["id"]
    verify_vehicle_documents(client, session, admin, vehicle_id)
    decided = client.post(
        f"/api/v1/admin/vehicles/{vehicle_id}/decide",
        json={"approve": True}, headers=admin,
    )
    assert decided.status_code == 200, decided.text
    return vehicle_id


def road_ready_driver(
    client: TestClient, admin: dict, phone: str, plate: str
) -> tuple[dict, str]:
    """A driver who can actually go online. Returns (headers, vehicle_id)."""
    session = auth(sign_in(client, phone))
    client.post("/api/v1/driver/register", json={}, headers=session)
    verify_driver_documents(client, session, admin)
    approve_driver(client, admin, phone)
    vehicle_id = register_and_activate_vehicle(client, session, admin, plate)
    return session, vehicle_id
