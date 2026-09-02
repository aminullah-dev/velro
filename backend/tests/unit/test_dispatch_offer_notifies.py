"""A dispatcher's offer reaches the driver it was made to.

The office presses Offer and the row is written. The driver's handset used to
learn of it only by polling GET /driver/offers every ten seconds -- and only
while its home screen was open. With the phone in a pocket, or on the
earnings screen, the offer expired unheard, and a scheduled departure went
undriven because the one man who could take it was told nothing.

A passenger's ask has always written an inbox row and attempted a push for
every driver it concerns (ADR 0005). These check the dispatch path now does
the same, once per driver and to his account rather than his driver id, and
that nothing about telling him can undo the offer itself.

No database. These are decisions about who is told, provable without one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from application.use_cases.dispatch import (
    Candidate,
    OfferTripCommand,
    OfferTripResult,
    OfferTripToDrivers,
)
from domain.enums import TripStatus

NOW = datetime(2026, 9, 2, 6, 0, tzinfo=UTC)
TRIP_ID = "01a05400-0000-7000-8000-0000000000aa"
TRIP_NUMBER = "VLR-2026-000123"


class FrozenClock:
    def now(self) -> datetime:
        return NOW


@dataclass
class TripStub:
    id: str = TRIP_ID
    number: str = TRIP_NUMBER
    status: str = TripStatus.SCHEDULED.value
    origin_station_id: str = "01a05400-0000-7000-8000-0000000000cc"
    seat_capacity: int = 4


class FakeTrips:
    def __init__(self, row: TripStub) -> None:
        self.row = row

    def get(self, trip_id: str) -> TripStub:
        return self.row


@dataclass(frozen=True)
class DriverStub:
    id: str
    user_id: str


class FakeDrivers:
    def __init__(self, drivers: list[DriverStub]) -> None:
        self.drivers = drivers

    def available_for(self, *, limit: int) -> list[DriverStub]:
        return list(self.drivers)


@dataclass
class OpenOffer:
    driver_id: str


@dataclass
class FakeOffers:
    """Offer rows, plus which drivers already hold one for this trip."""

    already: list[str] = field(default_factory=list)
    created: list[dict[str, Any]] = field(default_factory=list)

    def open_for_trips(self, ids: list[str], *, at: datetime) -> dict[str, list[OpenOffer]]:
        if not self.already:
            return {}
        return {TRIP_ID: [OpenOffer(driver_id=d) for d in self.already]}

    def create(self, **fields: Any) -> None:
        self.created.append(fields)


class FakeGeography:
    def get_station(self, station_id: str) -> None:
        return None


class EveryoneMatches:
    """Ranks every driver it is given, in the order given."""

    name = "everyone"

    def rank(self, *, trip, drivers, vehicles, locations, limit: int) -> list[Candidate]:
        return [
            Candidate(driver_id=d.id, vehicle_id=f"veh-{d.id}", distance_m=None, rank=i)
            for i, d in enumerate(drivers[:limit])
        ]


class FakeSettings:
    def get_int(self, key: str, default: int) -> int:
        return default


class FakeAudit:
    def write(self, *args: Any, **kwargs: Any) -> None:
        return None


class Listening:
    """Records every notify call, the way the real notifier writes a row."""

    def __init__(self) -> None:
        self.told: list[dict[str, Any]] = []

    def notify(self, **kwargs: Any) -> None:
        self.told.append(kwargs)


class Broken:
    def notify(self, **_: Any) -> None:
        raise RuntimeError("push is down")


HAULER = DriverStub(id="drv-1", user_id="usr-1")
RIVAL = DriverStub(id="drv-2", user_id="usr-2")


def offer(
    drivers: list[DriverStub], notifier: Any, *, already: list[str] | None = None
) -> tuple[OfferTripResult, FakeOffers]:
    offers = FakeOffers(already=already or [])
    use_case = OfferTripToDrivers(
        trips=FakeTrips(TripStub()),
        drivers=FakeDrivers(drivers),
        vehicles=object(),
        locations=object(),
        offers=offers,
        geography=FakeGeography(),
        matching=EveryoneMatches(),
        settings=FakeSettings(),
        audit=FakeAudit(),
        clock=FrozenClock(),
        new_id=lambda: f"offer-{len(offers.created)}",
        notifier=notifier,
    )
    result = use_case.execute(
        OfferTripCommand(trip_id=TRIP_ID, actor_id="01a05400-0000-7000-8000-0000000000ee")
    )
    return result, offers


class TestEveryDriverOfferedIsTold:
    def test_once_each_and_at_his_own_account(self) -> None:
        listening = Listening()
        result, _ = offer([HAULER, RIVAL], listening)

        assert result.offers_made == 2
        # The notification addresses the person, not the driver record: a
        # push and an inbox both hang off the user id.
        assert [t["user_id"] for t in listening.told] == ["usr-1", "usr-2"]

    def test_the_message_names_the_trip(self) -> None:
        listening = Listening()
        offer([HAULER], listening)

        (told,) = listening.told
        assert told["message_key"] == "notify.trip.offered"
        assert told["payload"]["trip_id"] == TRIP_ID
        assert told["payload"]["trip_number"] == TRIP_NUMBER
        assert told["payload"]["expires_in_seconds"] > 0
        # So the inbox row links to the trip the way an accepted fare's does.
        assert told["trip_id"] == TRIP_ID

    def test_a_driver_already_holding_the_offer_is_not_told_again(self) -> None:
        """The dispatcher's double tap: one card on the phone, one message."""
        listening = Listening()
        result, _ = offer([HAULER, RIVAL], listening, already=["drv-1"])

        assert result.driver_ids == ["drv-2"]
        assert [t["user_id"] for t in listening.told] == ["usr-2"]

    def test_nobody_left_to_offer_to_means_nobody_is_told(self) -> None:
        listening = Listening()
        result, _ = offer([HAULER], listening, already=["drv-1"])

        assert result.offers_made == 0
        assert listening.told == []


class TestTellingHimCanNeverCostTheOffer:
    def test_a_broken_notifier_leaves_every_offer_written(self) -> None:
        result, offers = offer([HAULER, RIVAL], Broken())

        assert result.offers_made == 2
        assert [row["driver_id"] for row in offers.created] == ["drv-1", "drv-2"]

    def test_no_notifier_at_all_is_still_an_offer(self) -> None:
        result, offers = offer([HAULER], None)

        assert result.offers_made == 1
        assert len(offers.created) == 1
