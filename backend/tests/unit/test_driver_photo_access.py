"""Who may look at a driver's face.

The photograph is an identity document. It is shown to a passenger because a
passenger deciding whether to get into a stranger's car on an empty road is
owed it -- not because passengers as a class are entitled to browse drivers.

So the rule is a live connection, not a role, and these hold it in place. If
this ever becomes "any signed-in user", the product has quietly turned every
driver's face into a public directory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ui.api.routers.documents import _LIVE_BOOKINGS, _passenger_may_see

PASSENGER = "user-1"
DRIVER = "driver-1"
OTHER_DRIVER = "driver-2"


@dataclass
class FakeRideRequests:
    open_request: Any = None

    def find_open_for_passenger(self, passenger_id, *, at=None):
        return self.open_request if passenger_id == PASSENGER else None


@dataclass
class FakeOffers:
    #: (request_id, driver_id) pairs that have an open offer
    open_pairs: set = field(default_factory=set)

    def open_for(self, ride_request_id, driver_id):
        return object() if (ride_request_id, driver_id) in self.open_pairs else None


@dataclass
class FakeBookings:
    rows: list = field(default_factory=list)

    def list_for_passenger(self, passenger_id, *, limit=20, statuses=None):
        if passenger_id != PASSENGER:
            return []
        return [b for b in self.rows if statuses is None or b.status in statuses]


@dataclass
class FakeTrips:
    rows: dict = field(default_factory=dict)

    def find(self, trip_id):
        return self.rows.get(trip_id)


@dataclass
class Row:
    id: str = "x"
    status: str = "CONFIRMED"
    trip_id: str | None = None
    driver_id: str | None = None


def may_see(*, requests=None, offers=None, bookings=None, trips=None, driver=DRIVER):
    return _passenger_may_see(
        PASSENGER, driver,
        ride_requests=requests or FakeRideRequests(),
        fare_offers=offers or FakeOffers(),
        bookings=bookings or FakeBookings(),
        trips=trips or FakeTrips(),
    )


class TestNoConnection:
    def test_a_stranger_is_refused(self):
        assert may_see() is False

    def test_an_open_request_with_no_offer_from_him_is_not_enough(self):
        # Asking for a ride does not entitle a passenger to every driver's face
        # -- only to the faces of the drivers who answered.
        assert may_see(
            requests=FakeRideRequests(open_request=Row(id="req-1")),
            offers=FakeOffers(open_pairs=set()),
        ) is False

    def test_an_offer_from_a_different_driver_does_not_open_this_one(self):
        assert may_see(
            requests=FakeRideRequests(open_request=Row(id="req-1")),
            offers=FakeOffers(open_pairs={("req-1", OTHER_DRIVER)}),
        ) is False


class TestOfferOnMyRequest:
    def test_a_driver_who_bid_on_my_request_may_be_seen(self):
        assert may_see(
            requests=FakeRideRequests(open_request=Row(id="req-1")),
            offers=FakeOffers(open_pairs={("req-1", DRIVER)}),
        ) is True


class TestBookingWithHim:
    def test_a_live_booking_on_his_trip_may_be_seen(self):
        assert may_see(
            bookings=FakeBookings([Row(status="DRIVER_ASSIGNED", trip_id="t-1")]),
            trips=FakeTrips({"t-1": Row(driver_id=DRIVER)}),
        ) is True

    def test_a_booking_on_someone_elses_trip_does_not(self):
        assert may_see(
            bookings=FakeBookings([Row(status="DRIVER_ASSIGNED", trip_id="t-1")]),
            trips=FakeTrips({"t-1": Row(driver_id=OTHER_DRIVER)}),
        ) is False

    def test_a_booking_with_no_trip_yet_does_not(self):
        assert may_see(
            bookings=FakeBookings([Row(status="CONFIRMED", trip_id=None)]),
            trips=FakeTrips(),
        ) is False

    def test_the_live_states_do_not_include_finished_or_cancelled_journeys(self):
        # A trip that ended is not a reason to keep reading his face. This is
        # the list the query filters on, so it is the thing worth asserting.
        assert "COMPLETED" not in _LIVE_BOOKINGS
        assert "CANCELLED" not in _LIVE_BOOKINGS
        assert "NO_SHOW" not in _LIVE_BOOKINGS
        assert set(_LIVE_BOOKINGS) == {
            "CONFIRMED", "DRIVER_ASSIGNED", "READY", "ONBOARD",
        }
