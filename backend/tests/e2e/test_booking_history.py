"""Booking history and the receipt, section 73.

A passenger opens this for two reasons: to find a journey they still have to
take, and to see the record of one they already took. The tests are written
along that split.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import auth, sign_in

RIDER = "+93700000060"


@pytest.fixture(scope="module")
def rider(client: TestClient) -> dict:
    return auth(sign_in(client, RIDER))


@pytest.fixture(scope="module")
def journey(client: TestClient, rider: dict) -> dict:
    """A trip that belongs to this module alone.

    These tests consume seats, and the seeded trips are shared -- the vertical
    slice asserts on an exact seat count, so booking from one of those makes
    this module's passing depend on the order the suite happens to run in. A
    trip published here is answerable to nobody else.
    """
    from datetime import timedelta

    from sqlalchemy import select

    from domain.enums import RideKind, TripStatus
    from infrastructure.db.models.routing import RouteRow, RouteStopRow
    from infrastructure.db.models.trips import TripRow, TripSeatRow, TripStopRow
    from infrastructure.services.numbers import SqlNumberAllocator
    from shared.clock import SystemClock
    from shared.ids import new_id
    from ui.api import deps

    with deps._session_factory()() as session:
        route = session.scalars(
            select(RouteRow).where(RouteRow.deleted_at.is_(None)).limit(1)
        ).one()
        stops = list(
            session.scalars(
                select(RouteStopRow)
                .where(RouteStopRow.route_id == route.id)
                .order_by(RouteStopRow.sequence)
            ).all()
        )
        # Far enough out that no other module's search window reaches it, and
        # the search window here is wide enough to still find it.
        departure = SystemClock().now() + timedelta(hours=6)
        trip = TripRow(
            id=new_id(),
            number=SqlNumberAllocator(session).allocate("trip", year=departure.year),
            route_id=route.id,
            ride_kind=RideKind.SHARED.value,
            seat_capacity=8,
            scheduled_departure_at=departure,
            status=TripStatus.SCHEDULED.value,
            origin_station_id=route.origin_station_id,
            destination_id=route.destination_id,
        )
        session.add(trip)
        session.flush()
        for stop in stops:
            session.add(
                TripStopRow(
                    id=new_id(), trip_id=trip.id, sequence=stop.sequence,
                    station_id=stop.station_id, destination_id=stop.destination_id,
                    planned_at=departure + timedelta(minutes=30 * stop.sequence),
                )
            )
        for seat_number in range(1, trip.seat_capacity + 1):
            session.add(TripSeatRow(id=new_id(), trip_id=trip.id, seat_number=seat_number))
        session.commit()

        return {
            "station_id": route.origin_station_id,
            "destination_id": route.destination_id,
            "trip_id": trip.id,
        }


def _book(
    client: TestClient, rider: dict, journey: dict, seats: int = 1, key: str = "one"
) -> dict:
    r = client.post(
        "/api/v1/bookings",
        json={
            "trip_id": journey["trip_id"],
            "seat_count": seats,
            "pickup_station_id": journey["station_id"],
            "dropoff_destination_id": journey["destination_id"],
        },
        # The key must differ per intended booking, or idempotency correctly
        # returns the first one and the test silently books nothing.
        headers={**rider, "Idempotency-Key": f"hist-{key}-{journey['trip_id'][-6:]}"},
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]


def _history(client: TestClient, rider: dict, **params) -> dict:
    r = client.get("/api/v1/bookings", headers=rider, params=params)
    assert r.status_code == 200, r.text
    return r.json()["data"]


@pytest.fixture(scope="module")
def booking(client: TestClient, rider: dict, journey: dict) -> dict:
    """One booking the read-only tests share.

    Every seat booked here is a seat another module cannot use, so the tests
    that only read are written against a single record.
    """
    return _book(client, rider, journey, key="shared")


# -- the list ------------------------------------------------------------

def test_history_is_a_page_not_a_bare_list(
    client: TestClient, rider: dict, journey: dict, booking: dict
) -> None:
    """The shape carries whether there is more.

    A bare array cannot say "there are older ones", so the screen either loads
    everything or silently truncates. Both are wrong on a slow connection.
    """
    data = _history(client, rider)
    assert isinstance(data, dict)
    assert isinstance(data["bookings"], list)
    assert data["has_more"] is False
    assert data["next_offset"] == len(data["bookings"])


def test_a_booking_carries_its_receipt(client: TestClient, rider: dict, booking: dict) -> None:
    booked = booking
    detail = client.get(f"/api/v1/bookings/{booked['id']}", headers=rider).json()["data"]

    assert detail["number"].startswith("BKG-")
    assert detail["fare_total"]["amount_minor"] > 0
    # The breakdown is what makes it a receipt rather than a total.
    assert detail["fare_breakdown"], "a receipt must show what the fare is made of"
    component = detail["fare_breakdown"][0]
    assert component["key"].startswith("fare.")
    assert component["amount"]["currency"] == detail["fare_total"]["currency"]
    # Components must account for the total, or the receipt contradicts itself.
    total = sum(c["amount"]["amount_minor"] * c["quantity"] for c in detail["fare_breakdown"])
    assert total == detail["fare_total"]["amount_minor"]

    assert detail["scheduled_departure_at"], "a passenger needs to know when"
    assert detail["trip_number"]
    # A receipt has to say where, on a handset that may never have downloaded
    # the geography snapshot.
    assert detail["pickup_station_name"], "a receipt must name where they boarded"
    assert detail["dropoff_destination_name"], "and where they were going"


def test_the_list_carries_the_same_receipt_as_the_detail(
    client: TestClient, rider: dict, booking: dict
) -> None:
    """So the history screen renders without a request per row."""
    booked = booking
    listed = next(
        b for b in _history(client, rider)["bookings"] if b["id"] == booked["id"]
    )
    detail = client.get(f"/api/v1/bookings/{booked['id']}", headers=rider).json()["data"]
    for field in (
        "fare_breakdown", "scheduled_departure_at", "trip_number",
        "seat_numbers", "driver_name", "vehicle_plate",
        "pickup_station_name", "dropoff_destination_name",
    ):
        assert listed[field] == detail[field], f"{field} differs between list and detail"


def test_upcoming_and_past_split_the_list(
    client: TestClient, rider: dict, booking: dict
) -> None:
    upcoming = _history(client, rider, scope="upcoming")["bookings"]
    past = _history(client, rider, scope="past")["bookings"]
    every = _history(client, rider, scope="all")["bookings"]

    assert upcoming, "a booking just made is upcoming"
    assert all(b["status"] in ("PENDING", "CONFIRMED", "DRIVER_ASSIGNED", "READY", "ONBOARD")
               for b in upcoming)
    assert all(b["status"] in ("COMPLETED", "CANCELLED", "NO_SHOW") for b in past)
    assert len(upcoming) + len(past) == len(every)


def test_every_status_lands_in_exactly_one_scope() -> None:
    """Checked against the declared statuses, not against whatever the tests
    happened to create -- a status in neither scope makes a booking invisible in
    both tabs, and no fixture would ever reveal it."""
    from domain.enums import BookingStatus
    from ui.api.routers.bookings import _SCOPES

    upcoming = set(_SCOPES["upcoming"])
    past = set(_SCOPES["past"])
    every = {s.value for s in BookingStatus}

    assert not (upcoming & past), f"in both scopes: {sorted(upcoming & past)}"
    assert upcoming | past == every, f"in neither scope: {sorted(every - upcoming - past)}"


def test_paging_does_not_repeat_a_booking(
    client: TestClient, rider: dict, journey: dict, booking: dict
) -> None:
    made = {booking["id"], _book(client, rider, journey, key="page-1")["id"]}
    assert len(made) == 2, "two distinct keys must make two distinct bookings"

    # limit=1 rather than more bookings: paging is about the boundary, and each
    # extra booking costs a seat the rest of the suite needs.
    first = _history(client, rider, limit=1)
    assert first["has_more"] is True
    second = _history(client, rider, limit=1, offset=first["next_offset"])
    ids = [b["id"] for b in first["bookings"]] + [b["id"] for b in second["bookings"]]
    assert len(ids) == len(set(ids))


def test_a_cancelled_booking_says_why_and_what_it_cost(
    client: TestClient, rider: dict, journey: dict
) -> None:
    booked = _book(client, rider, journey)
    cancelled = client.post(
        f"/api/v1/bookings/{booked['id']}/cancel",
        json={"reason_code": "PASSENGER_CANCELLED"},
        headers=rider,
    )
    assert cancelled.status_code == 200, cancelled.text

    detail = client.get(f"/api/v1/bookings/{booked['id']}", headers=rider).json()["data"]
    assert detail["status"] == "CANCELLED"
    assert detail["cancelled_at"]
    assert detail["cancellation_reason_code"] == "PASSENGER_CANCELLED"
    # Zero is a fee too: the passenger should be told they were not charged
    # rather than left to infer it from silence.
    assert detail["cancellation_fee"] is not None
    assert detail["cancellation_fee"]["amount_minor"] >= 0

    past = _history(client, rider, scope="past")["bookings"]
    assert any(b["id"] == booked["id"] for b in past)


# -- who may read it -----------------------------------------------------

def test_a_passenger_sees_only_their_own_bookings(
    client: TestClient, rider: dict, booking: dict, passenger_session: dict
) -> None:
    mine = booking
    theirs = _history(client, passenger_session)["bookings"]
    assert all(b["id"] != mine["id"] for b in theirs)

    denied = client.get(f"/api/v1/bookings/{mine['id']}", headers=passenger_session)
    assert denied.status_code == 403


def test_the_boarding_code_is_only_for_its_owner(
    client: TestClient, rider: dict, booking: dict, admin_session: dict
) -> None:
    mine = booking
    assert client.get(f"/api/v1/bookings/{mine['id']}", headers=rider).json()["data"][
        "verification_code"
    ]
    # Staff may read the booking, but the code boards a passenger.
    staff = client.get(f"/api/v1/bookings/{mine['id']}", headers=admin_session)
    assert staff.status_code == 200
    assert staff.json()["data"]["verification_code"] is None


def test_the_driver_is_reachable_while_the_ride_is_ahead_and_not_after(
    client: TestClient, admin_session: dict
) -> None:
    """Two people meeting at a station need to find each other.

    A receipt from last month does not, and leaving the number there turns the
    history screen into a directory of every driver she has ever ridden with.
    """
    from tests.e2e.conftest import auth, road_ready_driver, sign_in

    passenger = auth(sign_in(client, "+93700000195"))
    driver, _ = road_ready_driver(client, admin_session, "+93700000196", "PRW-1961")
    client.post("/api/v1/driver/status", headers=driver, json={"availability": "ONLINE"})

    districts = client.get("/api/v1/geo/districts", headers=passenger).json()["data"]
    journey = None
    for district in districts:
        for village in client.get(
            f"/api/v1/geo/districts/{district['id']}/villages", headers=passenger
        ).json()["data"]:
            for station in client.get(
                f"/api/v1/geo/villages/{village['id']}/stations", headers=passenger
            ).json()["data"]:
                destinations = client.get(
                    f"/api/v1/geo/stations/{station['id']}/destinations", headers=passenger
                ).json()["data"]
                if destinations:
                    journey = (station["id"], destinations[0]["id"])
                    break
            if journey:
                break
        if journey:
            break
    assert journey, "the seed produced no station with a destination"

    asked = client.post(
        "/api/v1/ride-requests", headers=passenger,
        json={
            "origin_station_id": journey[0], "destination_id": journey[1],
            "passenger_count": 1, "offered_fare_minor": 30_000,
        },
    ).json()["data"]
    offer = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        headers=driver, json={"amount_minor": 35_000},
    ).json()["data"]
    agreed = client.post(
        f"/api/v1/fare-offers/{offer['id']}/accept", headers=passenger
    ).json()["data"]

    live = client.get(
        f"/api/v1/bookings/{agreed['booking_id']}", headers=passenger
    ).json()["data"]
    assert live["driver_phone"], "she cannot reach the driver who is coming for her"

    # Now end it, and the number goes with the journey.
    client.post(
        f"/api/v1/bookings/{agreed['booking_id']}/cancel", headers=passenger,
        json={"reason_code": "PASSENGER_CANCELLED"},
    )
    finished = client.get(
        f"/api/v1/bookings/{agreed['booking_id']}", headers=passenger
    ).json()["data"]
    assert finished["driver_phone"] is None, (
        "a finished booking still carries the driver's number"
    )
