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
    ride_kind: str
    scheduled_departure_at: datetime
    #: Negative once the departure has passed. The board shows a trip a
    #: little while past its time because somebody is still waiting for it.
    minutes_to_departure: int
    #: Leaving within the at-risk window with nobody to drive it.
    at_risk: bool
    origin_station_id: str
    origin_station_name: str | None
    destination_id: str
    destination_name: str | None
    seat_capacity: int
    seats_available: int
    booked_seats: int
    #: Offers still on drivers' screens, and when the last of them lapses --
    #: as an instant, and as minutes from the snapshot so the browser never
    #: has to consult its own clock against the server's.
    open_offers: int
    offers_expire_at: datetime | None
    offers_expire_in_minutes: int | None
    #: Drivers online right now with an active car big enough. Zero means
    #: pressing Offer would achieve nothing, and the button says so.
    candidates: int


@router.get("/unassigned")
def unassigned_trips(
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    trips: Annotated[object, Depends(deps.trips)],
    offers: Annotated[object, Depends(deps.offers)],
    drivers: Annotated[object, Depends(deps.drivers)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
    settings: Annotated[object, Depends(deps.app_settings)],
    within_hours: Annotated[int, Query(ge=1, le=72)] = 12,
) -> dict:
    """Trips that need a driver, soonest first -- and what can be done about each.

    The dispatcher's working list. A trip number and a departure time were
    never enough to act on: the operator needs to know where it leaves from,
    how many people are already on it, whether drivers have been asked and
    are still deciding, and whether there is anybody online to ask at all.
    """
    now = deps.clock().now()
    at_risk_within = timedelta(minutes=settings.get_int("dispatch.at_risk_minutes", 60))

    pending = trips.needing_driver(now=now, horizon=timedelta(hours=within_hours))
    ids = [row.id for row in pending]
    availability = trips.seats_available_map(ids)
    names = trips.place_names(ids)
    open_offers = offers.open_for_trips(ids, at=now)

    # The supply, once: every online approved driver and the car he would
    # drive, then a count per trip of those big enough for it.
    pool = drivers.available_for(limit=100)
    cars = vehicles.active_by_driver([d.id for d in pool])
    capacities = sorted(car.seat_capacity for car in cars.values())

    board = []
    at_risk_count = 0
    for row in pending:
        minutes = int((row.scheduled_departure_at - now).total_seconds() // 60)
        at_risk = row.scheduled_departure_at <= now + at_risk_within
        at_risk_count += int(at_risk)
        offered = open_offers.get(row.id, [])
        last_offer = max((o.expires_at for o in offered), default=None)
        free = availability.get(row.id, 0)
        origin, destination = names.get(row.id, (None, None))
        board.append(
            UnassignedTripOut(
                id=row.id,
                number=row.number,
                status=row.status,
                ride_kind=row.ride_kind,
                scheduled_departure_at=row.scheduled_departure_at,
                minutes_to_departure=minutes,
                at_risk=at_risk,
                origin_station_id=row.origin_station_id,
                origin_station_name=origin,
                destination_id=row.destination_id,
                destination_name=destination,
                seat_capacity=row.seat_capacity,
                seats_available=free,
                booked_seats=row.seat_capacity - free,
                open_offers=len(offered),
                offers_expire_at=last_offer,
                offers_expire_in_minutes=(
                    max(0, int((last_offer - now).total_seconds() // 60))
                    if last_offer else None
                ),
                candidates=sum(1 for c in capacities if c >= row.seat_capacity),
            ).model_dump()
        )
    return ok(
        board,
        meta={
            "count": len(board),
            "at_risk": at_risk_count,
            "drivers_available": len(cars),
        },
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
