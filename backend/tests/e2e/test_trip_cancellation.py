"""What happens to a booking when its trip is called off.

The passenger is the one standing at the roadside. A trip that is cancelled,
expires, or never finds a driver is not coming, and until this existed the
booking stayed at DRIVER_ASSIGNED or READY -- so the app went on rendering the
boarding code under "Coming up" for a vehicle nobody was driving.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import auth, road_ready_driver, sign_in

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def rider(client: TestClient) -> dict:
    """A passenger of this module's own, signed in once.

    Signing in per test trips the OTP rate limiter, which is the server working
    correctly. Sharing the seeded passenger with test_vertical_slice makes both
    suites pass alone and fail together, so this one is separate.
    """
    return auth(sign_in(client, "+93700000175"))


def _booked_trip(
    client: TestClient, admin_session: dict, rider: dict, phone: str, plate: str
):
    """A passenger with a confirmed seat on a trip a driver has accepted."""
    passenger = rider
    driver, _ = road_ready_driver(client, admin_session, phone, plate)

    online = client.post(
        "/api/v1/driver/status", headers=driver, json={"availability": "ONLINE"}
    )
    assert online.status_code == 200, online.text

    # One open request per passenger, so tidy up anything a sibling test left.
    for row in client.get("/api/v1/ride-requests", headers=passenger).json()["data"]:
        if row["status"] == "OPEN":
            client.post(f"/api/v1/ride-requests/{row['id']}/cancel", headers=passenger)

    asked = client.post(
        "/api/v1/ride-requests", headers=passenger,
        json={
            **_journey(client, passenger),
            "passenger_count": 1,
            "offered_fare_minor": 20_000,
        },
    )
    assert asked.status_code == 201, asked.text
    request_id = asked.json()["data"]["id"]

    offered = client.post(
        f"/api/v1/driver/ride-requests/{request_id}/offer", headers=driver,
        json={"amount_minor": 25_000},
    )
    assert offered.status_code == 201, offered.text
    offer_id = offered.json()["data"]["id"]

    accepted = client.post(f"/api/v1/fare-offers/{offer_id}/accept", headers=passenger)
    assert accepted.status_code == 200, accepted.text
    return passenger, driver, accepted.json()["data"]


def _journey(client: TestClient, headers: dict) -> dict:
    """A real station with a real destination, walked out of the seed."""
    districts = client.get("/api/v1/geo/districts", headers=headers).json()["data"]
    for district in districts:
        villages = client.get(
            f"/api/v1/geo/districts/{district['id']}/villages", headers=headers
        ).json()["data"]
        for village in villages:
            stations = client.get(
                f"/api/v1/geo/villages/{village['id']}/stations", headers=headers
            ).json()["data"]
            for station in stations:
                destinations = client.get(
                    f"/api/v1/geo/stations/{station['id']}/destinations", headers=headers
                ).json()["data"]
                if destinations:
                    return {
                        "origin_station_id": station["id"],
                        "destination_id": destinations[0]["id"],
                    }
    pytest.skip("the seed produced no station with a destination")


def test_a_cancelled_trip_cancels_the_booking_riding_on_it(
    client: TestClient, admin_session: dict, rider: dict
) -> None:
    """The defect, stated as a test.

    TRIP_TO_BOOKING_STATUS mapped four of the twelve trip states and CANCELLED
    was not one of them, so cascade_bookings returned 0 and the booking was
    left exactly where it was -- with a live boarding code.
    """
    passenger, driver, result = _booked_trip(
        client, admin_session, rider, "+93700000170", "PRW-1701"
    )
    trip_id = result["trip_id"]
    booking_id = result["booking_id"]

    before = client.get(f"/api/v1/bookings/{booking_id}", headers=passenger).json()["data"]
    assert before["status"] == "DRIVER_ASSIGNED"

    cancelled = client.post(
        f"/api/v1/driver/trips/{trip_id}/advance", headers=driver,
        json={"target": "CANCELLED"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["data"]["status"] == "CANCELLED"

    after = client.get(f"/api/v1/bookings/{booking_id}", headers=passenger).json()["data"]
    assert after["status"] == "CANCELLED", (
        "the passenger is still holding a booking for a trip that is not coming"
    )


def test_the_passenger_is_told_their_trip_was_called_off(
    client: TestClient, admin_session: dict, rider: dict
) -> None:
    """A cancelled booking that nobody mentions is a passenger still waiting."""
    passenger, driver, result = _booked_trip(
        client, admin_session, rider, "+93700000171", "PRW-1711"
    )
    client.post(
        f"/api/v1/driver/trips/{result['trip_id']}/advance", headers=driver,
        json={"target": "CANCELLED"},
    )

    inbox = client.get("/api/v1/notifications", headers=passenger).json()["data"]
    keys = [n["message_key"] for n in inbox["notifications"]]
    assert any("cancel" in key for key in keys), (
        f"nothing in the passenger's inbox says the trip was called off: {keys}"
    )


def test_a_driver_cancellation_records_why(
    client: TestClient, admin_session: dict, rider: dict
) -> None:
    """A cancellation with no reason cannot be told from any other.

    A driver whose car broke down and one who simply changed their mind look
    identical afterwards -- and the second is the one that costs a passenger a
    morning, and the one a suspension has to be able to point at.
    """
    _, driver, result = _booked_trip(
        client, admin_session, rider, "+93700000172", "PRW-1721"
    )
    cancelled = client.post(
        f"/api/v1/driver/trips/{result['trip_id']}/advance", headers=driver,
        json={"target": "CANCELLED", "reason_code": "VEHICLE_PROBLEM",
              "note": "موتر خراب شد"},
    )
    assert cancelled.status_code == 200, cancelled.text

    from sqlalchemy import text

    from ui.api import deps

    with deps._session_factory()() as session:
        rows = session.execute(
            text(
                "SELECT reason_code, note, fee_minor, cancelled_by_role "
                "FROM cancellations WHERE trip_id = :trip"
            ),
            {"trip": result["trip_id"]},
        ).fetchall()

    assert rows, "the cancellation was not recorded at all"
    assert rows[0].reason_code == "VEHICLE_PROBLEM"
    assert rows[0].note == "موتر خراب شد"
    assert rows[0].cancelled_by_role == "DRIVER"
    # The passenger did not cancel; the ride was taken from them.
    assert rows[0].fee_minor == 0


def test_a_reason_the_platform_does_not_recognise_is_refused(
    client: TestClient, admin_session: dict, rider: dict
) -> None:
    """Free-text reason codes make the cancellation report meaningless."""
    _, driver, result = _booked_trip(
        client, admin_session, rider, "+93700000173", "PRW-1731"
    )
    response = client.post(
        f"/api/v1/driver/trips/{result['trip_id']}/advance", headers=driver,
        json={"target": "CANCELLED", "reason_code": "COULD_NOT_BE_BOTHERED"},
    )
    assert response.status_code == 422, response.text
