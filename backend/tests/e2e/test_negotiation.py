"""Agreeing a fare, section 89.

VELRO does not price a journey -- nobody knows the distance between two Ghorband
villages or which stretch of road is dirt. The passenger names a price, drivers
answer with theirs, the passenger picks one. These tests are about the rules of
that conversation, because a mistake in them is a mistake about money.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import auth, sign_in

RIDER = "+93700000100"
DRIVER_A = "+93700000101"
DRIVER_B = "+93700000102"


@pytest.fixture(scope="module")
def rider(client: TestClient) -> dict:
    return auth(sign_in(client, RIDER))


def _driver(client: TestClient, phone: str) -> dict:
    session = auth(sign_in(client, phone))
    client.post("/api/v1/driver/register", json={}, headers=session)
    return session


@pytest.fixture(scope="module")
def driver_a(client: TestClient) -> dict:
    return _driver(client, DRIVER_A)


@pytest.fixture(scope="module")
def driver_b(client: TestClient) -> dict:
    return _driver(client, DRIVER_B)


@pytest.fixture(scope="module")
def journey(client: TestClient, rider: dict) -> dict:
    """A real station and a real destination to travel between."""
    districts = client.get("/api/v1/geo/districts", headers=rider).json()["data"]
    for district in districts:
        villages = client.get(
            f"/api/v1/geo/districts/{district['id']}/villages", headers=rider
        ).json()["data"]
        for village in villages:
            stations = client.get(
                f"/api/v1/geo/villages/{village['id']}/stations", headers=rider
            ).json()["data"]
            for station in stations:
                destinations = client.get(
                    f"/api/v1/geo/stations/{station['id']}/destinations", headers=rider
                ).json()["data"]
                if destinations:
                    return {
                        "station_id": station["id"],
                        "destination_id": destinations[0]["id"],
                    }
    pytest.skip("the seed produced no station with a destination")


def _ask(client: TestClient, rider: dict, journey: dict, minor: int = 50_000) -> dict:
    r = client.post(
        "/api/v1/ride-requests",
        json={
            "origin_station_id": journey["station_id"],
            "destination_id": journey["destination_id"],
            "passenger_count": 1,
            "offered_fare_minor": minor,
        },
        headers=rider,
    )
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _clear(client: TestClient, rider: dict) -> None:
    """A passenger may only have one request open, so tests tidy up."""
    for row in client.get("/api/v1/ride-requests", headers=rider).json()["data"]:
        if row["status"] == "OPEN":
            client.post(f"/api/v1/ride-requests/{row['id']}/cancel", headers=rider)


# -- asking --------------------------------------------------------------

def test_a_passenger_names_their_own_price(
    client: TestClient, rider: dict, journey: dict
) -> None:
    _clear(client, rider)
    asked = _ask(client, rider, journey, 60_000)
    assert asked["status"] == "OPEN"
    assert asked["offered_fare"]["amount_minor"] == 60_000
    # Nothing was quoted at them: there is no server price to quote.
    assert asked["agreed_fare"] is None
    assert asked["origin_station_name"], "a request must say where from"
    assert asked["destination_name"]


def test_only_one_request_may_be_open_at_a_time(
    client: TestClient, rider: dict, journey: dict
) -> None:
    _clear(client, rider)
    _ask(client, rider, journey)
    again = client.post(
        "/api/v1/ride-requests",
        json={
            "origin_station_id": journey["station_id"],
            "destination_id": journey["destination_id"],
            "passenger_count": 1,
            "offered_fare_minor": 40_000,
        },
        headers=rider,
    )
    # Three live requests take three drivers off the board for one journey.
    assert again.status_code == 409
    _clear(client, rider)


# -- offering ------------------------------------------------------------

def test_a_driver_offers_and_the_passenger_sees_who(
    client: TestClient, rider: dict, driver_a: dict, journey: dict
) -> None:
    _clear(client, rider)
    asked = _ask(client, rider, journey, 50_000)

    offered = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 65_000, "note": "راه خامه است"},
        headers=driver_a,
    )
    assert offered.status_code == 201, offered.text
    assert offered.json()["data"]["amount"]["amount_minor"] == 65_000

    mine = client.get("/api/v1/ride-requests", headers=rider).json()["data"][0]
    assert len(mine["offers"]) == 1
    offer = mine["offers"][0]
    # A price with no name beside it is not a choice.
    assert offer["driver_name"] is not None or offer["driver_id"]
    assert offer["note"] == "راه خامه است"
    _clear(client, rider)


def test_a_driver_cannot_offer_twice_on_one_request(
    client: TestClient, rider: dict, driver_a: dict, journey: dict
) -> None:
    _clear(client, rider)
    asked = _ask(client, rider, journey)
    first = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 55_000}, headers=driver_a,
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 52_000}, headers=driver_a,
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "FARE_OFFER_ALREADY_MADE"
    _clear(client, rider)


def test_withdrawing_lets_a_driver_offer_again(
    client: TestClient, rider: dict, driver_a: dict, journey: dict
) -> None:
    """Changing your mind is withdrawing and offering again, so the passenger
    sees one number per driver rather than a negotiation to read through."""
    _clear(client, rider)
    asked = _ask(client, rider, journey)
    offer = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 70_000}, headers=driver_a,
    ).json()["data"]

    pulled = client.post(
        f"/api/v1/driver/fare-offers/{offer['id']}/withdraw", headers=driver_a
    )
    assert pulled.status_code == 200
    assert pulled.json()["data"]["status"] == "WITHDRAWN"

    again = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 58_000}, headers=driver_a,
    )
    assert again.status_code == 201, again.text
    _clear(client, rider)


def test_an_implausible_price_is_refused_before_it_reaches_the_roadside(
    client: TestClient, rider: dict, driver_a: dict, journey: dict
) -> None:
    """A missing zero or one too many. Refusing costs a retype; accepting costs
    an argument at the roadside."""
    _clear(client, rider)
    asked = _ask(client, rider, journey, 50_000)

    too_high = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 5_000_000}, headers=driver_a,
    )
    assert too_high.status_code == 422
    assert too_high.json()["error"]["code"] == "FARE_OFFER_IMPLAUSIBLE"
    assert too_high.json()["error"]["context"]["reason"] == "too_high"

    too_low = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 100}, headers=driver_a,
    )
    assert too_low.status_code == 422
    assert too_low.json()["error"]["context"]["reason"] == "too_low"
    _clear(client, rider)


def test_a_driver_cannot_bid_on_their_own_request(
    client: TestClient, driver_a: dict, journey: dict
) -> None:
    """One person manufacturing a completed trip would also manufacture a
    commission record and a rating."""
    _clear(client, driver_a)
    asked = _ask(client, driver_a, journey)
    r = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 50_000}, headers=driver_a,
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "FARE_OFFER_SELF"
    _clear(client, driver_a)


# -- agreeing ------------------------------------------------------------

def test_accepting_an_offer_creates_the_trip_at_the_agreed_price(
    client: TestClient, rider: dict, driver_a: dict, journey: dict
) -> None:
    _clear(client, rider)
    asked = _ask(client, rider, journey, 50_000)
    offer = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 65_000}, headers=driver_a,
    ).json()["data"]

    taken = client.post(f"/api/v1/fare-offers/{offer['id']}/accept", headers=rider)
    assert taken.status_code == 200, taken.text
    result = taken.json()["data"]

    # The agreed price, not the asking price.
    assert result["agreed_fare"]["amount_minor"] == 65_000
    assert result["trip_number"].startswith("VLR-")
    assert result["booking_number"].startswith("BKG-")
    assert result["verification_code"]

    booking = client.get(
        f"/api/v1/bookings/{result['booking_id']}", headers=rider
    ).json()["data"]
    assert booking["fare_total"]["amount_minor"] == 65_000
    # The receipt says what was agreed, and says it was agreed rather than
    # implying a calculation that never happened.
    assert booking["fare_breakdown"][0]["key"] == "fare.component.agreed"
    assert booking["fare_breakdown"][0]["amount"]["amount_minor"] == 65_000


def test_accepting_one_offer_tells_every_other_driver(
    client: TestClient, rider: dict, driver_a: dict, driver_b: dict, journey: dict
) -> None:
    """Otherwise they keep an offer that can never be accepted, and find out by
    driving to a station where nobody is waiting."""
    _clear(client, rider)
    asked = _ask(client, rider, journey, 50_000)
    a = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 60_000}, headers=driver_a,
    ).json()["data"]
    client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 55_000}, headers=driver_b,
    )

    assert client.post(
        f"/api/v1/fare-offers/{a['id']}/accept", headers=rider
    ).status_code == 200

    still_open = client.get("/api/v1/driver/fare-offers", headers=driver_b).json()["data"]
    assert all(o["ride_request_id"] != asked["id"] for o in still_open)


def test_a_passenger_cannot_accept_an_offer_on_someone_elses_request(
    client: TestClient, rider: dict, driver_a: dict, driver_b: dict, journey: dict
) -> None:
    _clear(client, rider)
    asked = _ask(client, rider, journey)
    offer = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 50_000}, headers=driver_a,
    ).json()["data"]

    stolen = client.post(f"/api/v1/fare-offers/{offer['id']}/accept", headers=driver_b)
    assert stolen.status_code == 403
    _clear(client, rider)


def test_a_matched_request_takes_no_more_offers(
    client: TestClient, rider: dict, driver_a: dict, driver_b: dict, journey: dict
) -> None:
    _clear(client, rider)
    asked = _ask(client, rider, journey, 50_000)
    offer = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 50_000}, headers=driver_a,
    ).json()["data"]
    client.post(f"/api/v1/fare-offers/{offer['id']}/accept", headers=rider)

    late = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 45_000}, headers=driver_b,
    )
    assert late.status_code == 409
    assert late.json()["error"]["code"] == "RIDE_REQUEST_NOT_OPEN"


# -- the driver's board --------------------------------------------------

def test_the_board_shows_waiting_passengers_oldest_first(
    client: TestClient, rider: dict, driver_a: dict, journey: dict
) -> None:
    _clear(client, rider)
    asked = _ask(client, rider, journey)

    board = client.get("/api/v1/driver/ride-requests", headers=driver_a)
    assert board.status_code == 200, board.text
    rows = board.json()["data"]
    mine = next(r for r in rows if r["id"] == asked["id"])
    assert mine["offered_fare"]["amount_minor"] == asked["offered_fare"]["amount_minor"]
    assert mine["already_offered"] is False
    # Someone has been waiting longest.
    created = [r["created_at"] for r in rows]
    assert created == sorted(created)
    _clear(client, rider)


def test_the_board_says_when_this_driver_has_already_offered(
    client: TestClient, rider: dict, driver_a: dict, journey: dict
) -> None:
    _clear(client, rider)
    asked = _ask(client, rider, journey)
    client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 50_000}, headers=driver_a,
    )
    rows = client.get("/api/v1/driver/ride-requests", headers=driver_a).json()["data"]
    assert next(r for r in rows if r["id"] == asked["id"])["already_offered"] is True
    _clear(client, rider)


# -- running out of time -------------------------------------------------

def test_an_expired_request_does_not_lock_the_passenger_out(
    client: TestClient, journey: dict
) -> None:
    """The worst failure this flow can have.

    A passenger asks, nobody answers, and the request sits OPEN for ever. Only
    one request may be open at a time, so they can never ask again -- the app
    is simply broken for them, with no error to explain it and nothing they can
    do. Nothing runs on a schedule here, so expiry has to happen when someone
    reads.
    """
    from datetime import timedelta

    from infrastructure.db.repositories.trips import RideRequestRepository
    from shared.clock import SystemClock
    from ui.api import deps

    session = auth(sign_in(client, "+93700000110"))
    asked = _ask(client, session, journey)

    # Push it past its deadline, as forty-five quiet minutes would.
    with deps._session_factory()() as db:
        requests = RideRequestRepository(db)
        row = requests.find(asked["id"])
        row.expires_at = SystemClock().now() - timedelta(minutes=1)
        db.commit()

    # Asking again directly, without reading the list first. A fresh install
    # goes straight here, so the ask path has to clear the way by itself rather
    # than relying on a screen having been opened.
    again = client.post(
        "/api/v1/ride-requests",
        json={
            "origin_station_id": journey["station_id"],
            "destination_id": journey["destination_id"],
            "passenger_count": 1,
            "offered_fare_minor": 50_000,
        },
        headers=session,
    )
    assert again.status_code == 201, again.text
    _clear(client, session)


def test_reading_a_stale_request_closes_it(client: TestClient, journey: dict) -> None:
    """The other half, tested apart from the first.

    Both the ask and the read clear stale requests, and either alone would save
    the passenger -- which means a regression in one would hide behind the
    other. They are checked separately so that cannot happen.
    """
    from datetime import timedelta

    from infrastructure.db.repositories.trips import RideRequestRepository
    from shared.clock import SystemClock
    from ui.api import deps

    session = auth(sign_in(client, "+93700000112"))
    asked = _ask(client, session, journey)
    with deps._session_factory()() as db:
        row = RideRequestRepository(db).find(asked["id"])
        row.expires_at = SystemClock().now() - timedelta(minutes=1)
        db.commit()

    # Reading alone, without asking again: a passenger staring at "waiting for
    # drivers" must not spin on a request that died an hour ago.
    listed = client.get("/api/v1/ride-requests", headers=session).json()["data"]
    assert any(r["id"] == asked["id"] and r["status"] == "EXPIRED" for r in listed)
    _clear(client, session)


def test_an_expired_request_is_off_the_drivers_board(
    client: TestClient, driver_a: dict, journey: dict
) -> None:
    from datetime import timedelta

    from infrastructure.db.repositories.trips import RideRequestRepository
    from shared.clock import SystemClock
    from ui.api import deps

    session = auth(sign_in(client, "+93700000111"))
    asked = _ask(client, session, journey)
    with deps._session_factory()() as db:
        requests = RideRequestRepository(db)
        row = requests.find(asked["id"])
        row.expires_at = SystemClock().now() - timedelta(minutes=1)
        db.commit()

    board = client.get("/api/v1/driver/ride-requests", headers=driver_a).json()["data"]
    assert all(r["id"] != asked["id"] for r in board)
    _clear(client, session)


# -- what support can see ------------------------------------------------

def test_support_can_see_who_is_waiting_and_what_they_were_offered(
    client: TestClient, driver_a: dict, journey: dict, admin_session: dict
) -> None:
    """A passenger ringing to say nobody will take them was unlookupable."""
    session = auth(sign_in(client, "+93700000113"))
    asked = _ask(client, session, journey, 45_000)
    client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 60_000}, headers=driver_a,
    )

    board = client.get("/api/v1/admin/ride-requests", headers=admin_session)
    assert board.status_code == 200, board.text
    row = next(r for r in board.json()["data"] if r["id"] == asked["id"])
    assert row["passenger_phone"], "an operator needs to know who is calling"
    assert row["offer_count"] == 1
    assert row["offers"][0]["amount"]["amount_minor"] == 60_000
    assert row["offered_fare"]["amount_minor"] == 45_000
    _clear(client, session)


def test_a_driver_cannot_read_the_operations_view(
    client: TestClient, driver_a: dict
) -> None:
    assert client.get(
        "/api/v1/admin/ride-requests", headers=driver_a
    ).status_code == 403


def test_there_is_no_way_for_staff_to_change_an_agreed_fare(client: TestClient) -> None:
    """The fare is between the passenger and the driver.

    An operator who could edit it would be a third party to a private
    agreement, so the operations view is read-only by construction -- there is
    no endpoint to write one, and this fails if someone adds one.
    """
    from ui.api.app import asgi

    writable = [
        path
        for path, ops in asgi.openapi()["paths"].items()
        if ("ride-request" in path or "fare-offer" in path)
        and path.startswith("/api/v1/admin")
        and any(m in ops for m in ("post", "put", "patch", "delete"))
    ]
    assert not writable, f"staff can write to a negotiation: {writable}"
