"""A seat is never sold on a vehicle whose departure has passed.

Status says whether the vehicle left. It says nothing about a trip whose
departure time came and went with nobody advancing it: SCHEDULED at 07:00,
still SCHEDULED at noon, and -- before this -- bookable by anyone holding its
id. The search never offered such a trip, so only a stale screen or a
hand-built request could reach it, but a seat sold on a vehicle that left
five hours ago is a seat sold on nothing, and the passenger finds out at the
roadside.

No database: this is a rule about a trip and a clock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from domain.enums import RideKind, TripStatus
from domain.trip import Trip, TripSeat
from shared.errors import ConflictError

DEPARTS = datetime(2026, 9, 2, 7, 0, tzinfo=UTC)


def _trip(status: TripStatus = TripStatus.SCHEDULED) -> Trip:
    return Trip(
        id="t1", number="VLR-2026-000001", route_id="r1", ride_kind=RideKind.SHARED,
        seat_capacity=4, scheduled_departure_at=DEPARTS, status=status,
        origin_station_id="s1", destination_id="d1",
        seats=[TripSeat(id=f"seat{n}", trip_id="t1", seat_number=n) for n in range(1, 5)],
    )


class TestTheClock:
    def test_before_departure_is_fine(self) -> None:
        _trip().assert_bookable(1, at=DEPARTS - timedelta(hours=2))

    def test_at_departure_is_too_late(self) -> None:
        """The departure minute itself: the vehicle is leaving, not waiting."""
        with pytest.raises(ConflictError) as refused:
            _trip().assert_bookable(1, at=DEPARTS)
        assert refused.value.code == "TRIP_DEPARTED"

    def test_after_departure_is_too_late_whatever_the_status_says(self) -> None:
        """The case this exists for: nobody advanced the trip."""
        with pytest.raises(ConflictError) as refused:
            _trip(TripStatus.SCHEDULED).assert_bookable(1, at=DEPARTS + timedelta(hours=5))
        assert refused.value.code == "TRIP_DEPARTED"
        assert refused.value.context["scheduled_departure_at"] == DEPARTS.isoformat()

    def test_a_driver_waiting_at_the_station_does_not_reopen_it(self) -> None:
        """ARRIVED_AT_PICKUP is bookable by status; the clock still rules."""
        with pytest.raises(ConflictError):
            _trip(TripStatus.ARRIVED_AT_PICKUP).assert_bookable(
                1, at=DEPARTS + timedelta(minutes=1)
            )

    def test_without_a_clock_the_old_rule_stands(self) -> None:
        """Callers that pass no ``at`` -- the domain tests, mainly -- keep
        the status-only check. The clock is opt-in, never assumed."""
        _trip().assert_bookable(1)


class TestTheOperatorsCutoff:
    def test_closes_that_many_minutes_before(self) -> None:
        trip, half_hour = _trip(), timedelta(minutes=30)
        trip.assert_bookable(1, at=DEPARTS - timedelta(minutes=31), closes_before=half_hour)
        with pytest.raises(ConflictError) as refused:
            trip.assert_bookable(1, at=DEPARTS - half_hour, closes_before=half_hour)
        assert refused.value.code == "TRIP_DEPARTED"
        assert refused.value.context["closes_before_minutes"] == 30

    def test_zero_is_the_departure_time_itself(self) -> None:
        _trip().assert_bookable(1, at=DEPARTS - timedelta(seconds=1), closes_before=timedelta(0))
        with pytest.raises(ConflictError):
            _trip().assert_bookable(1, at=DEPARTS, closes_before=timedelta(0))

    def test_the_clock_is_checked_before_the_seats(self) -> None:
        """A full trip that has also departed is departed first: the seat
        count is a detail of a trip nobody can book any more."""
        trip = _trip()
        for seat in trip.seats:
            seat.reserve("b1")
        with pytest.raises(ConflictError) as refused:
            trip.assert_bookable(1, at=DEPARTS + timedelta(hours=1))
        assert refused.value.code == "TRIP_DEPARTED"
