"""Asking for a car later, rather than now.

VELRO is not a hail-a-cab product. The journeys it exists for -- Ghorband to
Charikar, Ghorband to Kabul -- are arranged the evening before, because the car
leaves at six and nobody negotiates a fare at six. That is also the model of
every transfer marketplace: a request carries a departure time, drivers bid
against it, and the passenger picks.

The database column and the use-case field were both there from the start. The
API never passed anything, so `requested_for` was always `now` and every
request in the product meant "a car, immediately".

Wiring it through is two lines. What needed care is what those two lines let
in: a departure in the past, a departure next year, and -- the one that would
have shipped unnoticed -- a request for tomorrow morning that expires tonight,
because the deadline was `now + ttl` no matter what the passenger asked for.

No database here. These are decisions about time, and they should be provable
without one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from application.use_cases.negotiate_fare import (
    DEFAULT_REQUEST_TTL_MINUTES,
    RequestRide,
    RequestRideCommand,
)
from shared import error_codes
from shared.errors import ConflictError

NOW = datetime(2026, 8, 30, 17, 0, tzinfo=UTC)


class FrozenClock:
    def now(self) -> datetime:
        return NOW


@dataclass
class FakeRequests:
    rows: list[dict[str, Any]] = field(default_factory=list)

    def find_open_for_passenger(self, passenger_id: str, *, at: datetime):
        return None

    def create(self, **fields: Any) -> Any:
        self.rows.append(fields)
        return type("Row", (), fields)


class FakeGeography:
    def find_station(self, station_id: str) -> object:
        return object()

    def find_destination(self, destination_id: str) -> object:
        return object()


class FakeSettings:
    def get_int(self, key: str, default: int) -> int:
        return default


class FakeAudit:
    def write(self, *args: Any, **kwargs: Any) -> None:
        return None


def request(requested_for: datetime | None):
    requests = FakeRequests()
    use_case = RequestRide(
        requests=requests,
        geography=FakeGeography(),
        settings=FakeSettings(),
        audit=FakeAudit(),
        clock=FrozenClock(),
        new_id=lambda: "01a05400-0000-7000-8000-00000000000a",
    )
    use_case.execute(
        RequestRideCommand(
            passenger_id="01a05400-0000-7000-8000-00000000000b",
            origin_station_id="01a05400-0000-7000-8000-00000000000c",
            destination_id="01a05400-0000-7000-8000-00000000000d",
            passenger_count=1,
            offered_fare_minor=30000,
            requested_for=requested_for,
        )
    )
    return requests.rows[0]


class TestAnImmediateRequest:
    """The behaviour that already existed, which must not move."""

    def test_omitting_the_time_still_means_now(self) -> None:
        assert request(None)["requested_for"] == NOW

    def test_and_still_expires_on_the_ordinary_deadline(self) -> None:
        row = request(None)
        assert row["expires_at"] == NOW + timedelta(minutes=DEFAULT_REQUEST_TTL_MINUTES)


class TestAScheduledRequest:
    def test_keeps_the_departure_the_passenger_asked_for(self) -> None:
        tomorrow_six = NOW + timedelta(hours=13)
        assert request(tomorrow_six)["requested_for"] == tomorrow_six

    def test_stays_open_until_shortly_before_that_departure(self) -> None:
        """The bug this file was written for.

        Made at five in the afternoon for six the next morning, the request
        used to close at 17:45 -- before dinner, thirteen hours before the car
        was wanted, with the passenger still waiting and every driver locked
        out of a journey nobody had taken.
        """
        tomorrow_six = NOW + timedelta(hours=13)
        expires = request(tomorrow_six)["expires_at"]
        assert expires > NOW + timedelta(hours=12), (
            "a request for tomorrow must not close tonight"
        )
        assert expires < tomorrow_six, (
            "and must close before the car is due, not at it"
        )

    def test_a_departure_sooner_than_the_ttl_does_not_shorten_the_window(self) -> None:
        """A car wanted in ten minutes still gets the full bidding window.

        Taking `requested_for - lead` on its own would have closed this one in
        the past, which is why the deadline is the later of the two.
        """
        row = request(NOW + timedelta(minutes=10))
        assert row["expires_at"] == NOW + timedelta(minutes=DEFAULT_REQUEST_TTL_MINUTES)


class TestWhatTheFieldLetsIn:
    def test_a_departure_in_the_past_is_refused(self) -> None:
        with pytest.raises(ConflictError) as raised:
            request(NOW - timedelta(hours=2))
        assert raised.value.code == error_codes.RIDE_REQUEST_DEPARTURE_PAST

    def test_a_few_minutes_of_clock_drift_is_not_the_past(self) -> None:
        """Cheap handsets drift and a tap takes time to arrive. Refusing those
        would reject "now" from the phones most likely to be sending it."""
        row = request(NOW - timedelta(minutes=3))
        assert row["expires_at"] == NOW + timedelta(minutes=DEFAULT_REQUEST_TTL_MINUTES)

    def test_a_departure_beyond_the_horizon_is_refused(self) -> None:
        with pytest.raises(ConflictError) as raised:
            request(NOW + timedelta(days=90))
        assert raised.value.code == error_codes.RIDE_REQUEST_DEPARTURE_TOO_FAR

    def test_the_last_day_inside_the_horizon_is_accepted(self) -> None:
        row = request(NOW + timedelta(days=13, hours=23))
        assert row["requested_for"] == NOW + timedelta(days=13, hours=23)
