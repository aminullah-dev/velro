"""Dispatch.

The bridge between a trip that needs a driver and the drivers who could take
it. Section 89: a dispatcher sees unassigned trips and available drivers and
puts them together; section 90 defines the ordering.

Offering is a staff action here rather than an automatic one. Ghorband runs on
scheduled departures more than on hailing, so a person deciding which vehicle
covers which run is the real workflow -- and an automatic matcher that guesses
wrong strands passengers at a roadside.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from application.use_cases.dispatch import (
    NearestStationMatching,
    OfferTripCommand,
    OfferTripToDrivers,
)
from domain.enums import TripStatus
from ui.api import deps
from ui.api.errors import ok
from ui.api.schemas.common import Schema

router = APIRouter(prefix="/dispatch", tags=["dispatch"])


class OfferTripOut(Schema):
    trip_id: str
    offers_made: int
    driver_ids: list[str]


class UnassignedTripOut(Schema):
    id: str
    number: str
    status: str
    scheduled_departure_at: datetime
    origin_station_id: str
    destination_id: str
    seat_capacity: int
    seats_available: int
    booked_seats: int


@router.get("/unassigned")
def unassigned_trips(
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    trips: Annotated[object, Depends(deps.trips)],
    within_hours: Annotated[int, Query(ge=1, le=72)] = 12,
) -> dict:
    """Trips that need a driver, soonest first.

    The dispatcher's working list: what is departing and has nobody to drive it.
    """
    now = deps.clock().now()
    rows = trips.list(
        limit=100,
        driver_id=None,
    )
    horizon = now + timedelta(hours=within_hours)
    pending = [
        row
        for row in rows
        if row.driver_id is None
        and row.status in (TripStatus.SCHEDULED.value, TripStatus.REQUESTED.value)
        and row.scheduled_departure_at <= horizon
    ]
    pending.sort(key=lambda row: row.scheduled_departure_at)

    availability = trips.seats_available_map([row.id for row in pending])
    return ok(
        [
            UnassignedTripOut(
                id=row.id,
                number=row.number,
                status=row.status,
                scheduled_departure_at=row.scheduled_departure_at,
                origin_station_id=row.origin_station_id,
                destination_id=row.destination_id,
                seat_capacity=row.seat_capacity,
                seats_available=availability.get(row.id, 0),
                booked_seats=row.seat_capacity - availability.get(row.id, 0),
            ).model_dump()
            for row in pending
        ],
        meta={"count": len(pending)},
    )


@router.post("/trips/{trip_id}/offer")
def offer_trip(
    trip_id: str,
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    trips: Annotated[object, Depends(deps.trips)],
    drivers: Annotated[object, Depends(deps.drivers)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
    locations: Annotated[object, Depends(deps.driver_locations)],
    offers: Annotated[object, Depends(deps.offers)],
    geo: Annotated[object, Depends(deps.geography)],
    settings: Annotated[object, Depends(deps.app_settings)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    """Offer a trip to the drivers who could take it.

    Ranked by the section 90 ordering. Every offer expires, so a driver who put
    their phone down does not hold a trip nobody else can see.
    """
    use_case = OfferTripToDrivers(
        trips=trips,
        drivers=drivers,
        vehicles=vehicles,
        locations=locations,
        offers=offers,
        geography=geo,
        matching=NearestStationMatching(),
        settings=settings,
        audit=audit,
        clock=deps.clock(),
        new_id=deps.new_id,
    )
    result = use_case.execute(
        OfferTripCommand(trip_id=trip_id, actor_id=actor.user_id, actor_role=actor.role)
    )
    return ok(
        OfferTripOut(
            trip_id=result.trip_id,
            offers_made=result.offers_made,
            driver_ids=result.driver_ids,
        ).model_dump()
    )
