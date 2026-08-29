"""Agreeing a fare, section 89.

Passenger and driver endpoints in one file, because they are two halves of one
conversation and reading them apart hides whether they agree about what a price
means.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from application.use_cases.negotiate_fare import (
    AcceptOffer,
    AcceptOfferCommand,
    OfferFare,
    OfferFareCommand,
    RequestRide,
    RequestRideCommand,
    WithdrawOffer,
    WithdrawOfferCommand,
)
from domain.enums import RideRequestStatus
from shared import error_codes
from shared.errors import NotFoundError
from shared.money import Money
from ui.api import deps
from ui.api.errors import ok
from ui.api.schemas.common import MoneyOut, Schema


class RequestRideIn(Schema):
    origin_station_id: str
    destination_id: str
    passenger_count: int = Field(default=1, ge=1, le=8)
    # What the passenger is willing to pay, in minor units. There is no server
    # suggestion: VELRO does not know the distance or the state of the road.
    offered_fare_minor: int = Field(ge=1)
    vehicle_type_code: str | None = Field(default=None, max_length=24)
    note: str | None = Field(default=None, max_length=300)


class OfferFareIn(Schema):
    amount_minor: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=300)


class FareOfferOut(Schema):
    id: str
    ride_request_id: str
    driver_id: str
    amount: MoneyOut
    status: str
    note: str | None
    created_at: str
    # Who is offering. A price with no name beside it is not a choice.
    driver_name: str | None = None
    driver_rating: float | None = None
    driver_trips: int = 0
    vehicle_plate: str | None = None
    vehicle_description: str | None = None


class RideRequestOut(Schema):
    id: str
    status: str
    origin_station_id: str
    origin_station_name: str | None
    destination_id: str
    destination_name: str | None
    passenger_count: int
    offered_fare: MoneyOut
    agreed_fare: MoneyOut | None
    note: str | None
    expires_at: str
    created_at: str
    trip_id: str | None
    offers: list[FareOfferOut] = Field(default_factory=list)
    passenger_name: str | None = None


router = APIRouter(tags=["negotiation"])


# -- the passenger's side ------------------------------------------------

@router.post("/ride-requests", status_code=201)
def request_ride(
    body: RequestRideIn,
    actor: deps.ActorDep,
    requests: Annotated[object, Depends(deps.ride_requests)],
    geo: Annotated[object, Depends(deps.geography)],
    app_settings: Annotated[object, Depends(deps.app_settings)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    """Ask to be driven, at a price you name."""
    use_case = RequestRide(
        requests=requests, geography=geo, settings=app_settings, audit=audit,
        clock=deps.clock(), new_id=deps.new_id,
    )
    row = use_case.execute(
        RequestRideCommand(
            passenger_id=actor.user_id,
            origin_station_id=body.origin_station_id,
            destination_id=body.destination_id,
            passenger_count=body.passenger_count,
            offered_fare_minor=body.offered_fare_minor,
            vehicle_type_code=body.vehicle_type_code,
            note=body.note,
        )
    )
    return ok(_request_out(row, [], geo=geo).model_dump())


@router.get("/ride-requests")
def my_ride_requests(
    actor: deps.ActorDep,
    requests: Annotated[object, Depends(deps.ride_requests)],
    offers: Annotated[object, Depends(deps.fare_offers)],
    drivers: Annotated[object, Depends(deps.drivers)],
    users: Annotated[object, Depends(deps.users)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
    geo: Annotated[object, Depends(deps.geography)],
) -> dict:
    rows = requests.list_for_passenger(actor.user_id, limit=20)
    enricher = _OfferEnricher(drivers=drivers, users=users, vehicles=vehicles)
    return ok(
        [
            _request_out(
                row, enricher.decorate(offers.for_request(row.id)), geo=geo
            ).model_dump()
            for row in rows
        ]
    )


@router.post("/fare-offers/{offer_id}/accept")
def accept_offer(
    offer_id: str,
    actor: deps.ActorDep,
    requests: Annotated[object, Depends(deps.ride_requests)],
    offers: Annotated[object, Depends(deps.fare_offers)],
    trips: Annotated[object, Depends(deps.trips)],
    bookings: Annotated[object, Depends(deps.bookings)],
    seats: Annotated[object, Depends(deps.seats)],
    drivers: Annotated[object, Depends(deps.drivers)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
    routes: Annotated[object, Depends(deps.routes)],
    geo: Annotated[object, Depends(deps.geography)],
    numbers: Annotated[object, Depends(deps.numbers)],
    codes: Annotated[object, Depends(deps.verification_codes)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    """Take one driver's price. The journey exists from here."""
    use_case = AcceptOffer(
        requests=requests, offers=offers, trips=trips, bookings=bookings,
        seats=seats, drivers=drivers, vehicles=vehicles, routes=routes,
        geography=geo, numbers=numbers, codes=codes, audit=audit,
        clock=deps.clock(), new_id=deps.new_id,
    )
    result = use_case.execute(
        AcceptOfferCommand(offer_id=offer_id, passenger_id=actor.user_id)
    )
    return ok(
        {
            "ride_request_id": result.ride_request_id,
            "trip_id": result.trip_id,
            "trip_number": result.trip_number,
            "booking_id": result.booking_id,
            "booking_number": result.booking_number,
            "verification_code": result.verification_code,
            "driver_id": result.driver_id,
            "agreed_fare": MoneyOut.of(result.agreed_fare).model_dump(),
        }
    )


@router.post("/ride-requests/{request_id}/cancel")
def cancel_ride_request(
    request_id: str,
    actor: deps.ActorDep,
    requests: Annotated[object, Depends(deps.ride_requests)],
    offers: Annotated[object, Depends(deps.fare_offers)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    row = requests.find(request_id)
    if row is None or row.passenger_id != actor.user_id:
        raise NotFoundError(error_codes.RIDE_REQUEST_NOT_FOUND, ride_request_id=request_id)
    now = deps.clock().now()
    row.status = RideRequestStatus.CANCELLED.value
    row.version += 1
    requests.save(row)
    # Drivers who offered are told, rather than waiting on a request that is
    # gone.
    offers.decline_others(request_id=row.id, except_id="", at=now)
    audit.write(
        "ride_request.cancelled",
        actor_id=actor.user_id, actor_role=actor.role,
        entity_type="ride_request", entity_id=row.id,
    )
    return ok({"id": row.id, "status": row.status})


# -- the driver's side ---------------------------------------------------

driver_router = APIRouter(prefix="/driver", tags=["driver"])


@driver_router.get("/ride-requests")
def open_requests(
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    requests: Annotated[object, Depends(deps.ride_requests)],
    drivers: Annotated[object, Depends(deps.drivers)],
    users: Annotated[object, Depends(deps.users)],
    geo: Annotated[object, Depends(deps.geography)],
    offers: Annotated[object, Depends(deps.fare_offers)],
    station_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> dict:
    """Passengers waiting, and what each is offering to pay."""
    driver = drivers.find_by_user(actor.user_id)
    if driver is None:
        raise NotFoundError(error_codes.DRIVER_NOT_FOUND, user_id=actor.user_id)

    stations = [station_id] if station_id else None
    rows = requests.open_board(
        station_ids=stations, at=deps.clock().now(), limit=limit
    )
    mine = {o.ride_request_id for o in offers.open_for_driver(driver.id, limit=50)}
    passengers = {u.id: u for u in users.by_ids({r.passenger_id for r in rows})}
    return ok(
        [
            {
                **_request_out(row, [], geo=geo).model_dump(),
                "passenger_name": getattr(
                    passengers.get(row.passenger_id), "full_name", None
                ),
                # So the board can show "you have offered" rather than letting a
                # driver bid twice and meet a conflict.
                "already_offered": row.id in mine,
            }
            for row in rows
        ]
    )


@driver_router.post("/ride-requests/{request_id}/offer", status_code=201)
def offer_fare(
    request_id: str,
    body: OfferFareIn,
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    requests: Annotated[object, Depends(deps.ride_requests)],
    offers: Annotated[object, Depends(deps.fare_offers)],
    drivers: Annotated[object, Depends(deps.drivers)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    """Name your price. Offering exactly what was asked is agreeing to it."""
    use_case = OfferFare(
        requests=requests, offers=offers, drivers=drivers, vehicles=vehicles,
        audit=audit, clock=deps.clock(), new_id=deps.new_id,
    )
    offer = use_case.execute(
        OfferFareCommand(
            ride_request_id=request_id,
            driver_user_id=actor.user_id,
            amount_minor=body.amount_minor,
            note=body.note,
        )
    )
    return ok(
        FareOfferOut(
            id=offer.id, ride_request_id=offer.ride_request_id,
            driver_id=offer.driver_id, amount=MoneyOut.of(offer.amount),
            status=str(offer.status), note=offer.note,
            created_at=offer.created_at.isoformat() if offer.created_at else "",
        ).model_dump()
    )


@driver_router.post("/fare-offers/{offer_id}/withdraw")
def withdraw_offer(
    offer_id: str,
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    offers: Annotated[object, Depends(deps.fare_offers)],
    drivers: Annotated[object, Depends(deps.drivers)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    use_case = WithdrawOffer(
        offers=offers, drivers=drivers, audit=audit, clock=deps.clock()
    )
    offer = use_case.execute(
        WithdrawOfferCommand(offer_id=offer_id, driver_user_id=actor.user_id)
    )
    return ok({"id": offer.id, "status": str(offer.status)})


@driver_router.get("/fare-offers")
def my_offers(
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    offers: Annotated[object, Depends(deps.fare_offers)],
    drivers: Annotated[object, Depends(deps.drivers)],
) -> dict:
    driver = drivers.find_by_user(actor.user_id)
    if driver is None:
        raise NotFoundError(error_codes.DRIVER_NOT_FOUND, user_id=actor.user_id)
    return ok(
        [
            FareOfferOut(
                id=o.id, ride_request_id=o.ride_request_id, driver_id=o.driver_id,
                amount=MoneyOut.of(Money(o.amount_minor, o.amount_currency)),
                status=o.status, note=o.note,
                created_at=o.created_at.isoformat() if o.created_at else "",
            ).model_dump()
            for o in offers.open_for_driver(driver.id, limit=50)
        ]
    )


class _OfferEnricher:
    """Puts a name, a rating and a vehicle beside each price.

    Built once per request: a passenger comparing six offers would otherwise
    cost eighteen extra queries on a connection where each one is felt.
    """

    def __init__(self, *, drivers, users, vehicles) -> None:
        self._drivers = drivers
        self._users = users
        self._vehicles = vehicles

    def decorate(self, rows: list) -> list:
        driver_rows = {d.id: d for d in self._drivers.by_ids({r.driver_id for r in rows})}
        user_rows = {
            u.id: u for u in self._users.by_ids({d.user_id for d in driver_rows.values()})
        }
        vehicle_rows = {
            v.id: v
            for v in self._vehicles.by_ids({r.vehicle_id for r in rows if r.vehicle_id})
        }
        out = []
        for row in rows:
            driver = driver_rows.get(row.driver_id)
            user = user_rows.get(driver.user_id) if driver else None
            vehicle = vehicle_rows.get(row.vehicle_id) if row.vehicle_id else None
            rating = None
            if driver and driver.rating_count:
                rating = round(driver.rating_sum / driver.rating_count, 1)
            out.append(
                FareOfferOut(
                    id=row.id,
                    ride_request_id=row.ride_request_id,
                    driver_id=row.driver_id,
                    amount=MoneyOut.of(Money(row.amount_minor, row.amount_currency)),
                    status=row.status,
                    note=row.note,
                    created_at=row.created_at.isoformat() if row.created_at else "",
                    driver_name=user.full_name if user else None,
                    driver_rating=rating,
                    driver_trips=driver.completed_trips if driver else 0,
                    vehicle_plate=vehicle.plate_number if vehicle else None,
                    vehicle_description=_described(vehicle),
                )
            )
        return out


def _described(vehicle) -> str | None:
    if vehicle is None:
        return None
    parts = [vehicle.brand, vehicle.model, str(vehicle.year) if vehicle.year else None]
    return " ".join(p for p in parts if p) or None


def _request_out(row, offers, *, geo) -> RideRequestOut:
    station = geo.find_station(row.origin_station_id)
    destination = geo.find_destination(row.destination_id)
    return RideRequestOut(
        id=row.id,
        status=row.status,
        origin_station_id=row.origin_station_id,
        origin_station_name=getattr(station, "name", None),
        destination_id=row.destination_id,
        destination_name=getattr(destination, "name", None),
        passenger_count=row.passenger_count,
        offered_fare=MoneyOut.of(
            Money(row.offered_fare_minor, row.offered_fare_currency)
        ),
        agreed_fare=(
            MoneyOut.of(Money(row.agreed_fare_minor, row.offered_fare_currency))
            if row.agreed_fare_minor is not None
            else None
        ),
        note=row.note,
        expires_at=row.expires_at.isoformat(),
        created_at=row.created_at.isoformat() if row.created_at else "",
        trip_id=row.trip_id,
        offers=offers,
    )
