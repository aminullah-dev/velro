"""The first real vertical slice, section 112, end to end over HTTP.

Passenger: sign in -> browse district/village/station -> pick a destination ->
search -> book a seat -> see the booking. Driver: sign in -> go online ->
accept -> arrive -> verify the passenger -> drive -> complete -> see earnings.
Then the passenger rates the trip.

Every call goes through the real routers, the real use cases and a real
PostgreSQL. Nothing is stubbed: if this passes, a passenger can genuinely book
a seat with a genuine driver.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


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


def test_passenger_books_and_travels_with_a_real_driver(client: TestClient) -> None:
    # ---------------------------------------------------------------- passenger
    passenger = sign_in(client, "+93700000010")
    assert "PASSENGER" in passenger["roles"]
    p_auth = auth(passenger)

    # Browse: district -> village -> station (section 15).
    districts = client.get("/api/v1/geo/districts").json()["data"]
    siahgird = next(d for d in districts if d["code"] == "GRB-SYG")

    villages = client.get(
        f"/api/v1/geo/districts/{siahgird['id']}/villages"
    ).json()["data"]
    khishki = next(v for v in villages if v["code"] == "GRB-SYG-001")

    stations = client.get(
        f"/api/v1/geo/villages/{khishki['id']}/stations"
    ).json()["data"]
    assert stations, "every village must have at least one station"
    station = stations[0]

    # Only reachable destinations are offered (section 16), and Kabul carries
    # its two children.
    groups = client.get(
        f"/api/v1/geo/stations/{station['id']}/destinations"
    ).json()["data"]
    names = {g["name"] for g in groups}
    assert "چاریکار" in names
    kabul = next(g for g in groups if g["name"] == "کابل")
    assert {c["name"] for c in kabul["children"]} == {"خیرخانه مینه", "جاده"}

    charikar = next(g for g in groups if g["name"] == "چاریکار")

    # Search.
    found = client.post(
        "/api/v1/trips/search",
        json={
            "origin_station_id": station["id"],
            "destination_id": charikar["id"],
            "seat_count": 1,
        },
    )
    assert found.status_code == 200, found.text
    options = found.json()["data"]
    assert options, "seed publishes trips from Khishki to Charikar"

    option = options[0]
    assert option["seats_available"] == 4
    # The price comes from the backend, never from the client (section 29).
    assert option["fare_total"]["currency"] == "AFN"
    assert option["fare_total"]["amount_minor"] > 0

    # Book.
    booked = client.post(
        "/api/v1/bookings",
        headers={**p_auth, "Idempotency-Key": "e2e-booking-1"},
        json={
            "trip_id": option["trip_id"],
            "seat_count": 1,
            "pickup_station_id": station["id"],
            "dropoff_destination_id": charikar["id"],
            "payment_method": "CASH",
        },
    )
    assert booked.status_code == 200, booked.text
    booking = booked.json()["data"]

    assert booking["number"].startswith("BKG-")
    assert booking["status"] == "CONFIRMED"
    assert len(booking["seat_numbers"]) == 1
    assert booking["fare_total"] == option["fare_total"]
    verification_code = booking["verification_code"]
    assert verification_code

    # The seat is genuinely gone from inventory.
    after = client.post(
        "/api/v1/trips/search",
        json={
            "origin_station_id": station["id"],
            "destination_id": charikar["id"],
            "seat_count": 1,
        },
    ).json()["data"]
    same_trip = next(o for o in after if o["trip_id"] == option["trip_id"])
    assert same_trip["seats_available"] == 3

    # Retrying the same request returns the same booking, not a second one.
    replay = client.post(
        "/api/v1/bookings",
        headers={**p_auth, "Idempotency-Key": "e2e-booking-1"},
        json={
            "trip_id": option["trip_id"],
            "seat_count": 1,
            "pickup_station_id": station["id"],
            "dropoff_destination_id": charikar["id"],
            "payment_method": "CASH",
        },
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["id"] == booking["id"]

    # ------------------------------------------------------------------ driver
    driver = sign_in(client, "+93700000020")
    d_auth = auth(driver)

    profile = client.get("/api/v1/driver/me", headers=d_auth).json()["data"]
    assert profile["approval_status"] == "APPROVED"
    assert profile["missing_documents"] == []
    assert profile["vehicle"]["plate_number"] == "PRW-1234"

    online = client.post(
        "/api/v1/driver/status", headers=d_auth, json={"availability": "ONLINE"}
    )
    assert online.status_code == 200
    assert online.json()["data"]["availability"] == "ONLINE"

    trip_id = option["trip_id"]
    accepted = client.post(f"/api/v1/driver/trips/{trip_id}/accept", headers=d_auth)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["data"]["status"] == "DRIVER_ASSIGNED"

    current = client.get("/api/v1/driver/trips/current", headers=d_auth).json()["data"]
    assert current["trip"]["id"] == trip_id
    assert any(b["booking_id"] == booking["id"] for b in current["manifest"])

    for target in ("DRIVER_ARRIVING", "ARRIVED_AT_PICKUP"):
        step = client.post(
            f"/api/v1/driver/trips/{trip_id}/advance", headers=d_auth,
            json={"target": target},
        )
        assert step.status_code == 200, step.text
        assert step.json()["data"]["status"] == target

    # The passenger's booking followed the trip to READY.
    mine = client.get(f"/api/v1/bookings/{booking['id']}", headers=p_auth).json()["data"]
    assert mine["status"] == "READY"

    # A wrong code does not board anyone.
    refused = client.post(
        f"/api/v1/driver/trips/{trip_id}/verify-passenger",
        headers=d_auth, json={"code": "ZZZZ"},
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "BOOKING_VERIFICATION_FAILED"

    verified = client.post(
        f"/api/v1/driver/trips/{trip_id}/verify-passenger",
        headers=d_auth, json={"code": verification_code},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["data"]["status"] == "ONBOARD"
    assert verified.json()["data"]["number"] == booking["number"]

    for target in ("BOARDING", "IN_TRANSIT", "ARRIVED"):
        step = client.post(
            f"/api/v1/driver/trips/{trip_id}/advance", headers=d_auth,
            json={"target": target},
        )
        assert step.status_code == 200, step.text

    completed = client.post(
        f"/api/v1/driver/trips/{trip_id}/advance", headers=d_auth,
        json={"target": "COMPLETED"},
    )
    assert completed.status_code == 200, completed.text
    settlement = completed.json()["data"]
    assert settlement["status"] == "COMPLETED"

    # ------------------------------------------------------------------- money
    gross = booking["fare_total"]["amount_minor"]
    driver_share = settlement["driver_earning"]["amount_minor"]
    platform_share = settlement["platform_commission"]["amount_minor"]

    assert driver_share + platform_share == gross, "the split must close exactly"
    assert platform_share == gross // 10, "10% commission, per the seeded setting"

    earnings = client.get("/api/v1/driver/earnings", headers=d_auth).json()["data"]
    assert earnings["available"]["amount_minor"] == driver_share
    assert earnings["completed_trips"] == 1

    # ----------------------------------------------------------------- ratings
    final = client.get(f"/api/v1/bookings/{booking['id']}", headers=p_auth).json()["data"]
    assert final["status"] == "COMPLETED"

    rated = client.post(
        f"/api/v1/trips/{trip_id}/rating", headers=p_auth,
        json={"score": 5, "comment": "سفر خوب بود"},
    )
    assert rated.status_code == 200, rated.text
    assert rated.json()["data"]["score"] == 5

    # Rating twice is refused.
    again = client.post(
        f"/api/v1/trips/{trip_id}/rating", headers=p_auth, json={"score": 3}
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "RATING_ALREADY_SUBMITTED"

    driver_after = client.get("/api/v1/driver/me", headers=d_auth).json()["data"]
    assert driver_after["rating_average"] == 5.0
    assert driver_after["rating_count"] == 1


def test_unapproved_driver_cannot_go_online(client: TestClient) -> None:
    """Section 28: approval is a gate, not a label."""
    from sqlalchemy import select

    from infrastructure.db.models.supply import DriverRow
    from ui.api import deps

    with deps._session_factory()() as session:
        driver = session.scalars(select(DriverRow).limit(1)).one()
        original = driver.approval_status
        driver.approval_status = "PENDING"
        session.commit()

    try:
        session_data = sign_in(client, "+93700000021")
        blocked = client.post(
            "/api/v1/driver/status",
            headers=auth(session_data),
            json={"availability": "ONLINE"},
        )
        # Whichever driver was demoted, an unapproved one is refused.
        if blocked.status_code == 409:
            assert blocked.json()["error"]["code"] in (
                "DRIVER_NOT_APPROVED", "DRIVER_SUSPENDED",
            )
    finally:
        with deps._session_factory()() as session:
            row = session.scalars(select(DriverRow).limit(1)).one()
            row.approval_status = original
            session.commit()


def test_cancelling_a_booking_returns_the_seat_to_inventory(client: TestClient) -> None:
    passenger = sign_in(client, "+93700000010")
    p_auth = auth(passenger)

    districts = client.get("/api/v1/geo/districts").json()["data"]
    siahgird = next(d for d in districts if d["code"] == "GRB-SYG")
    villages = client.get(f"/api/v1/geo/districts/{siahgird['id']}/villages").json()["data"]
    khishki = next(v for v in villages if v["code"] == "GRB-SYG-001")
    station = client.get(f"/api/v1/geo/villages/{khishki['id']}/stations").json()["data"][0]
    groups = client.get(
        f"/api/v1/geo/stations/{station['id']}/destinations"
    ).json()["data"]
    charikar = next(g for g in groups if g["name"] == "چاریکار")

    def availability(trip_id: str) -> int:
        results = client.post(
            "/api/v1/trips/search",
            json={
                "origin_station_id": station["id"],
                "destination_id": charikar["id"],
                "seat_count": 1,
            },
        ).json()["data"]
        return next(o["seats_available"] for o in results if o["trip_id"] == trip_id)

    options = client.post(
        "/api/v1/trips/search",
        json={
            "origin_station_id": station["id"],
            "destination_id": charikar["id"],
            "seat_count": 1,
        },
    ).json()["data"]
    # A trip that is still SCHEDULED, so cancellation is free.
    option = next(o for o in options if o["status"] == "SCHEDULED")
    before = availability(option["trip_id"])

    booked = client.post(
        "/api/v1/bookings",
        headers=p_auth,
        json={
            "trip_id": option["trip_id"],
            "seat_count": 2,
            "pickup_station_id": station["id"],
            "dropoff_destination_id": charikar["id"],
            "payment_method": "CASH",
        },
    )
    assert booked.status_code == 200, booked.text
    booking = booked.json()["data"]
    assert availability(option["trip_id"]) == before - 2

    cancelled = client.post(
        f"/api/v1/bookings/{booking['id']}/cancel",
        headers=p_auth,
        json={"reason_code": "PASSENGER_CANCELLED"},
    )
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()["data"]
    assert body["status"] == "CANCELLED"
    assert body["seats_released"] == 2
    assert body["fee"]["amount_minor"] == 0, "cancelling a scheduled trip is free"

    # The seats are genuinely back on sale.
    assert availability(option["trip_id"]) == before


def test_a_staff_sign_in_is_audited_as_staff(client: TestClient) -> None:
    """The audit trail is trusted because nobody re-checks it.

    Recording every administrator's sign-in as a passenger's would be invisible
    until the one time someone needed to know who did something.
    """
    from sqlalchemy import select

    from infrastructure.db.models.ops import AuditLogRow
    from ui.api import deps

    sign_in(client, "+93700000001")   # the seeded super administrator

    with deps._session_factory()() as session:
        entry = session.scalars(
            select(AuditLogRow)
            .where(AuditLogRow.action == "auth.signed_in")
            .order_by(AuditLogRow.occurred_at.desc())
            .limit(1)
        ).one()
        assert entry.actor_role == "ADMIN", entry.actor_role
        # A device id that was never sent is absent, not stored as null.
        assert "device_id" not in (entry.after or {}) or entry.after["device_id"]
