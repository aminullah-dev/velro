"""Attacks that must fail.

Every test here is written from the attacker's side: it tries to do the thing,
and asserts the door is shut. A passing suite is not proof of security, but each
of these is a specific way this product could leak money or identity documents,
and none of them can regress silently.
"""

from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import auth, sign_in

MALLORY = "+93700000090"
VICTIM = "+93700000091"


@pytest.fixture(scope="module")
def mallory(client: TestClient) -> dict:
    session = auth(sign_in(client, MALLORY))
    client.post("/api/v1/driver/register", json={}, headers=session)
    return session


@pytest.fixture(scope="module")
def victim(client: TestClient) -> dict:
    session = auth(sign_in(client, VICTIM))
    client.post("/api/v1/driver/register", json={}, headers=session)
    return session


@pytest.fixture(scope="module")
def victim_driver_id(client: TestClient, victim: dict) -> str:
    return client.get("/api/v1/driver/me", headers=victim).json()["data"]["id"]


# -- money ---------------------------------------------------------------

def test_a_driver_cannot_read_another_drivers_wallet(
    client: TestClient, mallory: dict, victim_driver_id: str
) -> None:
    """There is no endpoint that takes a driver id for earnings, and there must
    not be: the wallet is always the caller's own."""
    for path in (
        "/api/v1/driver/earnings",
        "/api/v1/driver/earnings/ledger",
        "/api/v1/driver/settlements",
    ):
        mine = client.get(path, headers=mallory)
        assert mine.status_code == 200, mine.text
        # Nothing in the response may name another driver.
        assert victim_driver_id not in mine.text


def test_a_driver_cannot_collect_against_another_driver(
    client: TestClient, mallory: dict, victim_driver_id: str
) -> None:
    """Recording a collection clears a debt. A driver doing it for themselves,
    or for anyone, would be writing off money they owe."""
    r = client.post(
        "/api/v1/admin/settlements/collect",
        json={"driver_id": victim_driver_id},
        headers=mallory,
    )
    assert r.status_code == 403


def test_a_driver_cannot_decide_a_settlement(
    client: TestClient, mallory: dict, admin_session: dict
) -> None:
    from infrastructure.db.repositories.money import WalletRepository
    from ui.api import deps

    me = client.get("/api/v1/driver/me", headers=mallory).json()["data"]
    with deps._session_factory()() as session:
        wallets = WalletRepository(session)
        wallet = wallets.get_or_create(me["id"], "AFN")
        wallets.record_trip_settlement(
            wallet=wallet, platform_minor=5_000, driver_minor=45_000, cash=True
        )
        session.commit()

    created = client.post(
        "/api/v1/admin/settlements/collect",
        json={"driver_id": me["id"]},
        headers=admin_session,
    ).json()["data"]

    # Marking your own collection paid would clear a real debt for free.
    r = client.post(
        f"/api/v1/admin/settlements/{created['id']}/decide",
        json={"to": "PAID"},
        headers=mallory,
    )
    assert r.status_code == 403


def test_a_negative_payout_cannot_mint_money(client: TestClient) -> None:
    """A negative amount, if it reached the wallet, would move money the wrong
    way through a hold and leave the driver richer."""
    session = auth(sign_in(client, "+93700000092"))
    client.post("/api/v1/driver/register", json={}, headers=session)
    r = client.post(
        "/api/v1/driver/settlements", json={"amount_minor": -500_000}, headers=session
    )
    assert r.status_code == 422


# -- identity documents --------------------------------------------------

def test_a_driver_cannot_read_another_drivers_document(
    client: TestClient, mallory: dict, victim: dict
) -> None:
    """These are licences and national identity cards."""
    upload = client.post(
        "/api/v1/driver/documents",
        files={"file": ("id.png", _png(), "image/png")},
        data={"document_type_code": "NATIONAL_ID"},
        headers=victim,
    )
    assert upload.status_code in (200, 201), upload.text
    document_id = upload.json()["data"]["id"]

    stolen = client.get(f"/api/v1/driver/documents/{document_id}/file", headers=mallory)
    assert stolen.status_code == 404, "another driver's identity document"
    # 404 rather than 403, so the endpoint cannot be used to confirm which ids
    # exist. The owner still gets it.
    assert client.get(
        f"/api/v1/driver/documents/{document_id}/file", headers=victim
    ).status_code == 200


def test_a_driver_cannot_read_documents_through_the_admin_route(
    client: TestClient, mallory: dict, victim_driver_id: str
) -> None:
    r = client.get(f"/api/v1/admin/drivers/{victim_driver_id}/documents", headers=mallory)
    assert r.status_code == 403


def test_an_upload_is_judged_by_its_bytes_not_its_name(
    client: TestClient, mallory: dict
) -> None:
    """A declared content type is attacker-controlled. Storing a script because
    it claimed to be a PNG is how an upload directory becomes a shell."""
    r = client.post(
        "/api/v1/driver/documents",
        files={"file": ("licence.png", b"<?php system($_GET['c']); ?>", "image/png")},
        data={"document_type_code": "LICENSE"},
        headers=mallory,
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] in ("FILE_TYPE_UNSUPPORTED", "VALIDATION_FAILED")


def test_a_filename_cannot_escape_the_upload_directory(
    client: TestClient, mallory: dict
) -> None:
    r = client.post(
        "/api/v1/driver/documents",
        files={"file": ("../../../../etc/passwd.png", _png(), "image/png")},
        data={"document_type_code": "LICENSE"},
        headers=mallory,
    )
    # Either refused, or stored under a generated key -- never at the path the
    # uploader chose.
    if r.status_code in (200, 201):
        assert ".." not in r.text


# -- tokens --------------------------------------------------------------

def test_a_tampered_token_is_refused(client: TestClient, mallory: dict) -> None:
    """Re-signing is hard; editing the payload is not. The signature must be
    checked, not merely present."""
    token = mallory["Authorization"].removeprefix("Bearer ")
    header, payload, signature = token.split(".")

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    def unb64(part: str) -> dict:
        return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))

    claims = unb64(payload)
    claims["roles"] = ["ADMIN"]
    forged = f"{header}.{b64(json.dumps(claims).encode())}.{signature}"

    r = client.get("/api/v1/admin/dashboard", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_an_unsigned_token_is_refused(client: TestClient, mallory: dict) -> None:
    """The alg=none attack: a token that says it needs no signature."""
    token = mallory["Authorization"].removeprefix("Bearer ")
    _, payload, _ = token.split(".")
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "none", "typ": "JWT"}).encode()
    ).decode().rstrip("=")

    r = client.get(
        "/api/v1/admin/dashboard",
        headers={"Authorization": f"Bearer {header}.{payload}."},
    )
    assert r.status_code == 401


def test_a_missing_token_is_refused_everywhere_that_matters(client: TestClient) -> None:
    for method, path in (
        ("get", "/api/v1/driver/earnings"),
        ("get", "/api/v1/bookings"),
        ("get", "/api/v1/admin/settlements/debtors"),
        ("post", "/api/v1/driver/settlements"),
    ):
        r = getattr(client, method)(path, **({"json": {}} if method == "post" else {}))
        assert r.status_code == 401, f"{method.upper()} {path} answered {r.status_code}"


# -- personal data -------------------------------------------------------

def test_an_error_never_returns_a_full_phone_number(client: TestClient) -> None:
    """The OTP limiter reports who is being limited. A full number in an error
    body is a number an unauthenticated caller can harvest."""
    phone = "+93700000093"
    for _ in range(5):
        r = client.post("/api/v1/auth/otp/request", json={"phone": phone})
        if r.status_code != 200:
            body = r.text
            assert phone not in body, "a full phone number reached an error body"
            assert "***" in body or "*" in body
            return
    pytest.fail("the OTP limiter did not engage")


def test_the_boarding_code_is_not_returned_to_staff(
    client: TestClient, admin_session: dict
) -> None:
    """Staff can read a booking for support. The code boards a passenger, so it
    is not part of what support needs.

    The booking is made here rather than borrowed from another module: a
    security test that skips because someone else's fixture did not run is a
    test that proves nothing.
    """
    rider = auth(sign_in(client, "+93700000094"))
    booking = _a_booking(client, rider)
    assert booking["verification_code"], "the owner sees their own code"

    staff = client.get(f"/api/v1/bookings/{booking['id']}", headers=admin_session)
    assert staff.status_code == 200
    assert staff.json()["data"]["verification_code"] is None


def test_a_passenger_cannot_read_another_passengers_booking(
    client: TestClient, mallory: dict
) -> None:
    rider = auth(sign_in(client, "+93700000095"))
    booking = _a_booking(client, rider)
    r = client.get(f"/api/v1/bookings/{booking['id']}", headers=mallory)
    assert r.status_code == 403


def _a_booking(client: TestClient, rider: dict) -> dict:
    """One booking on a trip published for this module alone."""
    from datetime import timedelta

    from domain.enums import RideKind, TripStatus
    from infrastructure.db.models.routing import RouteRow, RouteStopRow
    from infrastructure.db.models.trips import TripRow, TripSeatRow, TripStopRow
    from infrastructure.services.numbers import SqlNumberAllocator
    from shared.clock import SystemClock
    from shared.ids import new_id
    from sqlalchemy import select
    from ui.api import deps

    with deps._session_factory()() as session:
        route = session.scalars(
            select(RouteRow).where(RouteRow.deleted_at.is_(None)).limit(1)
        ).one()
        stops = list(session.scalars(
            select(RouteStopRow).where(RouteStopRow.route_id == route.id)
            .order_by(RouteStopRow.sequence)
        ).all())
        departure = SystemClock().now() + timedelta(hours=5)
        trip = TripRow(
            id=new_id(),
            number=SqlNumberAllocator(session).allocate("trip", year=departure.year),
            route_id=route.id, ride_kind=RideKind.SHARED.value, seat_capacity=2,
            scheduled_departure_at=departure, status=TripStatus.SCHEDULED.value,
            origin_station_id=route.origin_station_id,
            destination_id=route.destination_id,
        )
        session.add(trip)
        session.flush()
        for stop in stops:
            session.add(TripStopRow(
                id=new_id(), trip_id=trip.id, sequence=stop.sequence,
                station_id=stop.station_id, destination_id=stop.destination_id,
                planned_at=departure + timedelta(minutes=30 * stop.sequence),
            ))
        for n in (1, 2):
            session.add(TripSeatRow(id=new_id(), trip_id=trip.id, seat_number=n))
        session.commit()
        trip_id, station_id = trip.id, route.origin_station_id
        destination_id = route.destination_id

    made = client.post(
        "/api/v1/bookings",
        json={
            "trip_id": trip_id, "seat_count": 1,
            "pickup_station_id": station_id,
            "dropoff_destination_id": destination_id,
        },
        headers={**rider, "Idempotency-Key": f"sec-{trip_id[-8:]}"},
    )
    assert made.status_code in (200, 201), made.text
    return made.json()["data"]


def _png() -> bytes:
    """The smallest valid PNG, so uploads are tested with real bytes."""
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
        "IQAAAABJRU5ErkJggg=="
    )
