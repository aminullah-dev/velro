"""Agreeing a fare, section 89.

VELRO does not price a journey -- nobody knows the distance between two Ghorband
villages or which stretch of road is dirt. The passenger names a price, drivers
answer with theirs, the passenger picks one. These tests are about the rules of
that conversation, because a mistake in them is a mistake about money.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.e2e.conftest import auth, road_ready_driver, sign_in

RIDER = "+93700000100"
# The seeded drivers, not freshly-registered ones.
#
# These fixtures used to sign in a new number and POST /driver/register, which
# leaves a driver PENDING with no vehicle -- and every test here passed,
# because the negotiated path had no gate: a person who had merely asked to
# become a driver could bid on a real journey and win it. The scheduled path
# has always checked approval, availability, an active vehicle and whether he
# is already carrying somebody. Now both do, so these fixtures have to be
# drivers who could actually turn up.
DRIVER_A = "+93700000020"
DRIVER_B = "+93700000021"


@pytest.fixture(scope="module")
def rider(client: TestClient) -> dict:
    return auth(sign_in(client, RIDER))


def _driver(client: TestClient, phone: str) -> dict:
    """An approved driver, with a vehicle, online -- one who can take work."""
    session = auth(sign_in(client, phone))
    client.post(
        "/api/v1/driver/status", json={"availability": "ONLINE"}, headers=session
    )
    return session


@pytest.fixture(scope="module")
def driver_a(client: TestClient, admin_session: dict) -> dict:
    session, _ = road_ready_driver(
        client, admin_session, "+93700000101", "NEG-1101"
    )
    client.post(
        "/api/v1/driver/status", json={"availability": "ONLINE"}, headers=session
    )
    return session


@pytest.fixture(scope="module")
def driver_b(client: TestClient, admin_session: dict) -> dict:
    session, _ = road_ready_driver(
        client, admin_session, "+93700000102", "NEG-1102"
    )
    client.post(
        "/api/v1/driver/status", json={"availability": "ONLINE"}, headers=session
    )
    return session


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


def _ask(
    client: TestClient,
    rider: dict,
    journey: dict,
    minor: int = 50_000,
    *,
    return_minor: int | None = None,
    return_for: str | None = None,
) -> dict:
    body = {
        "origin_station_id": journey["station_id"],
        "destination_id": journey["destination_id"],
        "passenger_count": 1,
        "offered_fare_minor": minor,
    }
    if return_minor is not None:
        body["return_fare_minor"] = return_minor
    if return_for is not None:
        body["return_for"] = return_for
    r = client.post("/api/v1/ride-requests", json=body, headers=rider)
    assert r.status_code == 201, r.text
    return r.json()["data"]


def _release(client, *drivers) -> None:
    """Put every driver back to idle and online."""
    for driver in drivers:
        trip = client.get("/api/v1/driver/trips/current", headers=driver)
        data = trip.json().get("data") if trip.status_code == 200 else None
        if data and data.get("trip"):
            client.post(
                f"/api/v1/driver/trips/{data['trip']['id']}/advance",
                headers=driver, json={"target": "CANCELLED"},
            )
        client.post(
            "/api/v1/driver/status", json={"availability": "ONLINE"}, headers=driver
        )


@pytest.fixture(autouse=True)
def _idle_drivers(client: TestClient, driver_a: dict, driver_b: dict):
    """Both drivers idle before and after every test in this module.

    A driver may hold only one live trip since the negotiated path started
    checking it, so a test that accepts an offer leaves its driver carrying a
    passenger. Cleaning up afterwards as well as before matters because these
    are the seeded drivers: leaving one mid-trip at the end of this module
    breaks the vertical-slice test that signs in as the same man.
    """
    _release(client, driver_a, driver_b)
    yield
    _release(client, driver_a, driver_b)


def _clear(client: TestClient, rider: dict, *drivers: dict) -> None:
    """Tidy up between tests.

    A passenger may hold only one open request, and -- since the negotiated
    path started checking it -- a driver may hold only one live trip. Any test
    that accepts an offer therefore leaves its driver carrying a passenger, and
    the next test in the module finds him correctly refused. Releasing him here
    is what lets these fixtures stay module-scoped.
    """
    for row in client.get("/api/v1/ride-requests", headers=rider).json()["data"]:
        if row["status"] == "OPEN":
            client.post(f"/api/v1/ride-requests/{row['id']}/cancel", headers=rider)
    for driver in drivers:
        trip = client.get("/api/v1/driver/trips/current", headers=driver)
        if trip.status_code != 200:
            continue
        data = trip.json().get("data")
        if data:
            client.post(
                f"/api/v1/driver/trips/{data['id']}/advance",
                headers=driver, json={"target": "CANCELLED"},
            )


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


def test_asking_twice_says_what_is_wrong_and_where_to_go(
    client: TestClient, rider: dict, journey: dict
) -> None:
    """The refusal a passenger actually meets, and the one she could not read.

    It used to raise BOOKING_LIMIT_REACHED with limit=1. That code's sentence
    interpolates {maximum}, so the placeholder rendered raw — "You already have
    {maximum} active bookings." — and it spoke of bookings she does not have.
    She has one open ask, and what she needs is the route back to it.
    """
    _clear(client, rider)
    first = _ask(client, rider, journey, 40_000)

    second = client.post(
        "/api/v1/ride-requests",
        json={
            "origin_station_id": journey["station_id"],
            "destination_id": journey["destination_id"],
            "passenger_count": 1,
            "offered_fare_minor": 45_000,
        },
        headers=rider,
    )
    assert second.status_code == 409, second.text
    error = second.json()["error"]
    assert error["code"] == "RIDE_REQUEST_ALREADY_OPEN"
    # The id travels with it, so the app can offer the way back rather than
    # only the refusal.
    assert error["context"]["ride_request_id"] == first["id"]


def test_the_refusal_has_a_sentence_with_no_placeholder_left_in_it(
    client: TestClient,
) -> None:
    """A message key whose parameters are never supplied reads as {maximum}."""
    import json
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "backend" / "resources" / "locales"
    for locale in ("en", "fa-AF", "ps"):
        messages = json.loads((root / f"{locale}.json").read_text(encoding="utf-8"))
        sentence = messages["error.ride_request_already_open"]
        assert not re.search(r"\{\w+\}", sentence), (
            f"{locale}: the sentence expects a parameter the server does not send"
        )


# -- the way back --------------------------------------------------------

def _tomorrow(hour: int) -> str:
    from datetime import datetime, timedelta, timezone

    kabul = timezone(timedelta(hours=4, minutes=30))
    when = (datetime.now(kabul) + timedelta(days=1)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    return when.isoformat()


def test_a_round_trip_is_agreed_at_the_price_of_both_legs(
    client: TestClient, rider: dict, driver_a: dict, journey: dict
) -> None:
    """The rule that decides what the passenger actually pays.

    A round trip is argued as two numbers and settled as one. Taking the
    outbound alone would book the journey at half its price and leave the
    driver's return fare with nobody -- and the trip, the commission, the
    wallet and the receipt would all agree with each other and all be wrong.
    """
    _clear(client, rider)
    asked = _ask(
        client, rider, journey,
        minor=30_000,
        return_minor=25_000,
        return_for=_tomorrow(14),
    )
    assert asked["offered_fare"]["amount_minor"] == 30_000
    assert asked["return_fare"]["amount_minor"] == 25_000

    offer = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 35_000, "return_amount_minor": 30_000},
        headers=driver_a,
    )
    assert offer.status_code in (200, 201), offer.text
    offer = offer.json()["data"]
    assert offer["amount"]["amount_minor"] == 35_000
    assert offer["return_amount"]["amount_minor"] == 30_000

    # Read back the way the app reads it. The reply to the driver's POST is
    # not what the passenger sees: she sees her own request with the offers
    # attached, and that listing built the offer separately -- so it shipped
    # the outbound leg alone while this test, checking only the POST, passed.
    mine = client.get("/api/v1/ride-requests", headers=rider).json()["data"][0]
    listed = mine["offers"][0]
    assert listed["amount"]["amount_minor"] == 35_000
    assert listed["return_amount"]["amount_minor"] == 30_000, (
        "the offers a passenger chooses between must carry both legs"
    )

    taken = client.post(f"/api/v1/fare-offers/{offer['id']}/accept", headers=rider)
    assert taken.status_code == 200, taken.text
    result = taken.json()["data"]

    # 350 out and 300 back is 650, not 350.
    assert result["agreed_fare"]["amount_minor"] == 65_000

    booking = client.get(
        f"/api/v1/bookings/{result['booking_id']}", headers=rider
    ).json()["data"]
    assert booking["fare_total"]["amount_minor"] == 65_000


def test_a_matched_request_cannot_be_cancelled_out_from_under_its_trip(
    client: TestClient, rider: dict, driver_a: dict, journey: dict
) -> None:
    """Cancelling the ask must not orphan the journey.

    This wrote CANCELLED over whatever the status was. A matched request has a
    trip, a booking, held seats and a driver already on his way; marking it
    dead here left every one of those running. The passenger's screen said the
    ride was cancelled, the driver's said he had a passenger, and the seats
    stayed held for a journey nobody was taking.
    """
    _clear(client, rider)
    asked = _ask(client, rider, journey, 30_000)
    offer = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 30_000}, headers=driver_a,
    ).json()["data"]
    client.post(f"/api/v1/fare-offers/{offer['id']}/accept", headers=rider)

    refused = client.post(
        f"/api/v1/ride-requests/{asked['id']}/cancel", headers=rider
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "RIDE_REQUEST_NOT_OPEN"


def test_an_open_request_can_still_be_withdrawn(
    client: TestClient, rider: dict, journey: dict
) -> None:
    """The ordinary case, unchanged."""
    _clear(client, rider)
    asked = _ask(client, rider, journey, 30_000)
    done = client.post(f"/api/v1/ride-requests/{asked['id']}/cancel", headers=rider)
    assert done.status_code == 200, done.text
    assert done.json()["data"]["status"] == "CANCELLED"


def test_a_driver_who_may_not_work_cannot_bid(
    client: TestClient, rider: dict, admin_session: dict, journey: dict
) -> None:
    """The gate the scheduled path always had and this one never did.

    dispatch.py has always checked approval, availability, an active vehicle
    and whether the driver is already carrying somebody, before letting him
    take a scheduled trip. The negotiated path -- which is how rides actually
    happen in VELRO -- checked none of them. A person who had merely asked to
    become a driver could bid on a real journey and win it, and every test in
    this file passed while that was true, because the fixtures registered
    exactly such a person.
    """
    unapproved = auth(sign_in(client, "+93700000109"))
    client.post("/api/v1/driver/register", json={}, headers=unapproved)
    _clear(client, rider)
    asked = _ask(client, rider, journey, 30_000)
    refused = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 30_000}, headers=unapproved,
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "DRIVER_NOT_APPROVED"


def test_a_driver_already_carrying_someone_cannot_win_a_second_ride(
    client: TestClient, rider: dict, driver_a: dict, journey: dict
) -> None:
    """Two passengers, one car, and the second invisible to him.

    Nothing declined a driver's other open offers when he won one, and nothing
    checked whether he was already on a trip -- so he could be matched twice
    and only ever see the first. The second passenger would be told a driver
    was assigned and stand at the station.
    """
    _clear(client, rider)
    first = _ask(client, rider, journey, 30_000)
    offer = client.post(
        f"/api/v1/driver/ride-requests/{first['id']}/offer",
        json={"amount_minor": 30_000}, headers=driver_a,
    ).json()["data"]
    client.post(f"/api/v1/fare-offers/{offer['id']}/accept", headers=rider)

    # He is now carrying somebody. A second request must not reach him.
    second_rider = auth(sign_in(client, "+93700000108"))
    _clear(client, second_rider)
    second = _ask(client, second_rider, journey, 30_000)
    refused = client.post(
        f"/api/v1/driver/ride-requests/{second['id']}/offer",
        json={"amount_minor": 30_000}, headers=driver_a,
    )
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "DRIVER_ALREADY_ON_TRIP"
    _clear(client, second_rider)


def test_a_journey_velro_has_not_modelled_can_still_be_agreed(
    client: TestClient, rider: dict, driver_a: dict
) -> None:
    """A negotiated ride does not need a route, and now the schema agrees.

    RouteRepository.find_for has always said in its own docstring that "a
    negotiated ride does not need one -- two people agreed to make the journey
    whether or not VELRO has modelled it -- so this returns None ... and the
    trip simply carries no route", and AcceptOffer wrote route_id=None on that
    basis. trips.route_id was NOT NULL, so the database refused: an
    IntegrityError, a 500, and a passenger tapping "take this car" getting a
    server error she could repeat for ever. On production 20 of the 90
    station-to-destination pairs had no active route -- better than a fifth of
    every journey the valley can ask for.

    This test picks a pair deliberately: the destination NOT offered for the
    station, which is exactly the pair no route was generated for.
    """
    districts = client.get("/api/v1/geo/districts", headers=rider).json()["data"]
    unrouted = None
    for district in districts:
        villages = client.get(
            f"/api/v1/geo/districts/{district['id']}/villages", headers=rider
        ).json()["data"]
        for village in villages:
            stations = client.get(
                f"/api/v1/geo/villages/{village['id']}/stations", headers=rider
            ).json()["data"]
            for station in stations:
                offered = {
                    d["id"] for d in client.get(
                        f"/api/v1/geo/stations/{station['id']}/destinations",
                        headers=rider,
                    ).json()["data"]
                }
                everywhere = client.get(
                    "/api/v1/geo/snapshot", headers=rider
                ).json()["data"]["destinations"]
                for d in everywhere:
                    if d["id"] not in offered:
                        unrouted = {"station_id": station["id"], "destination_id": d["id"]}
                        break
                if unrouted:
                    break
            if unrouted:
                break
        if unrouted:
            break
    if unrouted is None:
        pytest.skip("the seed routes every station to every destination")

    _clear(client, rider)
    asked = _ask(client, rider, unrouted, minor=30_000)
    offer = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 30_000}, headers=driver_a,
    ).json()["data"]
    taken = client.post(f"/api/v1/fare-offers/{offer['id']}/accept", headers=rider)
    assert taken.status_code == 200, (
        f"an unmodelled journey must still be agreeable, got {taken.status_code}: "
        f"{taken.text[:300]}"
    )
    assert taken.json()["data"]["trip_number"].startswith("VLR-")


def test_a_round_trip_stays_a_round_trip_after_it_is_agreed(
    client: TestClient, rider: dict, driver_a: dict, journey: dict
) -> None:
    """The return has to survive acceptance.

    It survived the whole negotiation -- asked for, priced, bid on, agreed,
    charged -- and then ceased to exist at the moment the trip was created.
    The trip carried one departure, the driver's assignment showed one leg,
    and the passenger's booking showed one date, for a journey she had paid
    for twice. The only row that still knew was the closed ride_request
    nobody reads again.
    """
    _clear(client, rider)
    back = _tomorrow(14)
    asked = _ask(
        client, rider, journey,
        minor=30_000, return_minor=25_000, return_for=back,
    )
    offer = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 30_000, "return_amount_minor": 25_000},
        headers=driver_a,
    ).json()["data"]
    result = client.post(
        f"/api/v1/fare-offers/{offer['id']}/accept", headers=rider
    ).json()["data"]

    booking = client.get(
        f"/api/v1/bookings/{result['booking_id']}", headers=rider
    ).json()["data"]
    assert booking["return_for"] is not None, (
        "the booking must say when the car comes back, because she paid for it"
    )
    assert booking["return_for"].startswith(back[:10])


def test_a_one_way_booking_carries_no_return_date(
    client: TestClient, rider: dict, driver_a: dict, journey: dict
) -> None:
    _clear(client, rider)
    asked = _ask(client, rider, journey, minor=30_000)
    offer = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 30_000}, headers=driver_a,
    ).json()["data"]
    result = client.post(
        f"/api/v1/fare-offers/{offer['id']}/accept", headers=rider
    ).json()["data"]
    booking = client.get(
        f"/api/v1/bookings/{result['booking_id']}", headers=rider
    ).json()["data"]
    assert booking["return_for"] is None


def test_a_driver_sees_both_legs_in_his_own_offers(
    client: TestClient, rider: dict, driver_a: dict, journey: dict
) -> None:
    """The list behind "you offered X" on the driver's board.

    A third place that builds an offer for the wire, and the third place that
    could quietly send the outbound leg alone -- telling a driver who had just
    named 350 and 300 that he had offered 350.
    """
    _clear(client, rider)
    asked = _ask(
        client, rider, journey,
        minor=30_000, return_minor=25_000, return_for=_tomorrow(14),
    )
    client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 35_000, "return_amount_minor": 30_000},
        headers=driver_a,
    )
    mine = client.get("/api/v1/driver/fare-offers", headers=driver_a).json()["data"]
    row = next(o for o in mine if o["ride_request_id"] == asked["id"])
    assert row["amount"]["amount_minor"] == 35_000
    assert row["return_amount"]["amount_minor"] == 30_000


def test_a_driver_must_price_the_return_that_was_asked_for(
    client: TestClient, rider: dict, driver_a: dict, journey: dict
) -> None:
    """Answering only the outbound is answering a different question."""
    _clear(client, rider)
    asked = _ask(
        client, rider, journey,
        minor=30_000, return_minor=25_000, return_for=_tomorrow(14),
    )
    refused = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 35_000},
        headers=driver_a,
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "FARE_OFFER_RETURN_MISMATCH"


def test_a_driver_may_not_price_a_return_nobody_asked_for(
    client: TestClient, rider: dict, driver_a: dict, journey: dict
) -> None:
    _clear(client, rider)
    asked = _ask(client, rider, journey, minor=30_000)
    refused = client.post(
        f"/api/v1/driver/ride-requests/{asked['id']}/offer",
        json={"amount_minor": 35_000, "return_amount_minor": 20_000},
        headers=driver_a,
    )
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "FARE_OFFER_RETURN_MISMATCH"


def test_a_one_way_journey_carries_no_return_fare(
    client: TestClient, rider: dict, journey: dict
) -> None:
    _clear(client, rider)
    asked = _ask(client, rider, journey, minor=30_000)
    assert asked["return_fare"] is None
    assert asked["return_for"] is None
