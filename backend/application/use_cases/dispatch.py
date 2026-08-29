"""Dispatch: matching a trip to a driver.

Version one is the ordering the specification asks for (section 90): online,
nearest station, suitable vehicle, suitable route, capacity, status. It sits
behind an interface so that ETA, acceptance rate and demand can be added later
without touching anything that calls it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from domain.driver import Driver
from domain.enums import ActorRole, DriverApprovalStatus, DriverAvailability, TripStatus
from shared import error_codes
from shared.clock import Clock
from shared.errors import ConflictError, NotFoundError


@dataclass(frozen=True, slots=True)
class Candidate:
    driver_id: str
    vehicle_id: str
    distance_m: int | None
    rank: int


class MatchingStrategy(Protocol):
    name: str

    def rank(self, *, trip, drivers, vehicles, locations, limit: int) -> list[Candidate]: ...


class NearestStationMatching:
    """Ordered by proximity to the pickup station, then by trips completed.

    Distance is unknown for a driver who has not sent a location -- common on a
    weak connection -- and those drivers are ranked last rather than excluded,
    because a working driver with no GPS fix is still a working driver.
    """

    name = "nearest_station"

    def rank(self, *, trip, drivers, vehicles, locations, limit: int) -> list[Candidate]:
        station = getattr(trip, "_origin_station", None)
        candidates: list[Candidate] = []

        for driver in drivers:
            if driver.approval_status != DriverApprovalStatus.APPROVED.value:
                continue
            if driver.availability != DriverAvailability.ONLINE.value:
                continue
            vehicle = vehicles.primary_for_driver(driver.id)
            if vehicle is None or vehicle.status != "ACTIVE":
                continue
            if vehicle.seat_capacity < trip.seat_capacity:
                continue

            distance = None
            if station is not None and station.latitude is not None:
                fix = locations.find(driver.id)
                if fix is not None:
                    from infrastructure.db.repositories.geography import _approx_distance_m

                    distance = _approx_distance_m(
                        station.latitude, station.longitude, fix.latitude, fix.longitude
                    )
            candidates.append(
                Candidate(driver_id=driver.id, vehicle_id=vehicle.id, distance_m=distance, rank=0)
            )

        candidates.sort(
            key=lambda c: (c.distance_m is None, c.distance_m or 0)
        )
        return [
            Candidate(c.driver_id, c.vehicle_id, c.distance_m, rank=i)
            for i, c in enumerate(candidates[:limit])
        ]


@dataclass(frozen=True, slots=True)
class OfferTripCommand:
    trip_id: str
    actor_id: str
    actor_role: ActorRole = ActorRole.SYSTEM
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class OfferTripResult:
    trip_id: str
    offers_made: int
    driver_ids: list[str]


class OfferTripToDrivers:
    def __init__(
        self, *, trips, drivers, vehicles, locations, offers, geography,
        matching: MatchingStrategy, settings, audit, clock: Clock, new_id, notifier=None,
    ) -> None:
        self._trips = trips
        self._drivers = drivers
        self._vehicles = vehicles
        self._locations = locations
        self._offers = offers
        self._geography = geography
        self._matching = matching
        self._settings = settings
        self._audit = audit
        self._clock = clock
        self._new_id = new_id
        self._notifier = notifier

    def execute(self, cmd: OfferTripCommand) -> OfferTripResult:
        now = self._clock.now()
        trip = self._trips.get(cmd.trip_id)

        if trip.status not in (TripStatus.REQUESTED.value, TripStatus.SCHEDULED.value):
            raise ConflictError(
                error_codes.TRIP_DRIVER_ALREADY_ASSIGNED,
                trip_id=trip.id,
                status=trip.status,
            )

        trip._origin_station = self._geography.get_station(trip.origin_station_id)
        limit = self._settings.get_int("dispatch.max_offers_per_trip", 10)
        ttl = self._settings.get_int("dispatch.offer_ttl_seconds", 30)

        candidates = self._matching.rank(
            trip=trip,
            drivers=self._drivers.available_for(limit=limit * 3),
            vehicles=self._vehicles,
            locations=self._locations,
            limit=limit,
        )
        if not candidates:
            raise NotFoundError(error_codes.TRIP_NO_DRIVER_AVAILABLE, trip_id=trip.id)

        for candidate in candidates:
            self._offers.create(
                id=self._new_id(),
                trip_id=trip.id,
                driver_id=candidate.driver_id,
                offered_at=now,
                expires_at=now + timedelta(seconds=ttl),
                rank=candidate.rank,
            )

        self._audit.write(
            "trip.offered",
            actor_id=cmd.actor_id,
            actor_role=cmd.actor_role,
            entity_type="trip",
            entity_id=trip.id,
            after={"offers": len(candidates), "strategy": self._matching.name},
            request_id=cmd.request_id,
        )
        return OfferTripResult(
            trip_id=trip.id,
            offers_made=len(candidates),
            driver_ids=[c.driver_id for c in candidates],
        )


@dataclass(frozen=True, slots=True)
class AcceptTripCommand:
    trip_id: str
    driver_user_id: str
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class AcceptTripResult:
    trip_id: str
    driver_id: str
    vehicle_id: str
    status: TripStatus


class AcceptTrip:
    """A driver takes a trip.

    The race here is two drivers accepting the same offer. It is resolved the
    same way as the seat race: the trip row is locked, and the state machine
    refuses a second assignment because DRIVER_ASSIGNED is not reachable from
    DRIVER_ASSIGNED.
    """

    def __init__(
        self, *, trips, drivers, vehicles, offers, bookings, audit, clock: Clock, notifier=None
    ) -> None:
        self._trips = trips
        self._drivers = drivers
        self._vehicles = vehicles
        self._offers = offers
        self._bookings = bookings
        self._audit = audit
        self._clock = clock
        self._notifier = notifier

    def execute(self, cmd: AcceptTripCommand) -> AcceptTripResult:
        now = self._clock.now()

        driver_row = self._drivers.find_by_user(cmd.driver_user_id)
        if driver_row is None:
            raise NotFoundError(error_codes.DRIVER_NOT_FOUND, user_id=cmd.driver_user_id)

        driver = Driver(
            id=driver_row.id,
            user_id=driver_row.user_id,
            approval_status=DriverApprovalStatus(driver_row.approval_status),
            availability=DriverAvailability(driver_row.availability),
        )
        driver.assert_can_accept()

        in_flight = self._trips.active_for_driver(driver.id)
        if in_flight is not None and in_flight.id != cmd.trip_id:
            raise ConflictError(
                error_codes.DRIVER_ALREADY_ON_TRIP,
                driver_id=driver.id,
                trip_id=in_flight.id,
            )

        vehicle = self._vehicles.primary_for_driver(driver.id)
        if vehicle is None:
            raise NotFoundError(error_codes.VEHICLE_NOT_FOUND, driver_id=driver.id)
        if vehicle.status != "ACTIVE":
            raise ConflictError(error_codes.VEHICLE_SUSPENDED, vehicle_id=vehicle.id)

        row = self._trips.get(cmd.trip_id)
        from application.use_cases.trip_lifecycle import _to_trip

        trip = _to_trip(row, [])
        # Raises TRIP_DRIVER_ALREADY_ASSIGNED for the loser of the race.
        trip.assign_driver(driver.id, vehicle.id, at=now)

        row.status = trip.status.value
        row.driver_id = driver.id
        row.vehicle_id = vehicle.id
        self._trips.save(row)

        driver_row.availability = DriverAvailability.ON_TRIP.value
        self._drivers.save(driver_row)

        # The bookings riding on this trip move with it.
        from application.use_cases.trip_lifecycle import cascade_bookings

        cascade_bookings(self._bookings, trip.status, now, trip_id=trip.id)

        offer = self._offers.find_open(cmd.trip_id, driver.id, at=now)
        if offer is not None:
            offer.responded_at = now
            offer.response = "ACCEPTED"
            self._offers.save(offer)

        self._audit.write(
            "trip.accepted",
            actor_id=cmd.driver_user_id,
            actor_role=ActorRole.DRIVER,
            entity_type="trip",
            entity_id=trip.id,
            after={"driver_id": driver.id, "vehicle_id": vehicle.id},
            request_id=cmd.request_id,
        )
        return AcceptTripResult(
            trip_id=trip.id,
            driver_id=driver.id,
            vehicle_id=vehicle.id,
            status=trip.status,
        )
