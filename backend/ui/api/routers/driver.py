"""Driver endpoints.

Every one of these is gated on the driver role, and the use cases behind them
check that the driver owns the trip. A driver app is a phone in a vehicle on a
road; it will be out of date, retried and occasionally hostile.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header

from application.use_cases.dispatch import AcceptTrip, AcceptTripCommand
from application.use_cases.trip_lifecycle import (
    AdvanceTrip,
    AdvanceTripCommand,
    VerifyPassenger,
    VerifyPassengerCommand,
)
from domain.enums import (
    ActorRole,
    DriverAvailability,
    TripStatus,
    VehicleStatus,
)
from shared import error_codes
from shared.errors import ConflictError, NotFoundError
from shared.money import Money
from ui.api import deps
from ui.api import mapdata
from ui.api.errors import ok
from ui.api.idempotency import idempotent
from ui.api.schemas.common import MoneyOut
from ui.api.schemas.driver import (
    AdvanceTripIn,
    AdvanceTripOut,
    DriverProfileOut,
    DriverStatusIn,
    EarningsOut,
    LocationPingIn,
    TripSummaryOut,
    VehicleOut,
    VerifyPassengerIn,
    VerifyPassengerOut,
)

router = APIRouter(prefix="/driver", tags=["driver"])


@router.get("/me")
def driver_profile(
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
    users: Annotated[object, Depends(deps.users)],
    settings: Annotated[object, Depends(deps.app_settings)],
) -> dict:
    from application.use_cases.driver_documents import _to_driver

    row = _driver_of(drivers, actor.user_id)
    user = users.get(row.user_id)
    vehicle = vehicles.current_for_driver(row.id)

    # Built through the shared mapper so this uses the one implementation of
    # "which documents are still missing". A second copy of that rule here is
    # how the endpoint went on reporting nothing missing after the rule was
    # corrected everywhere else -- only the newest upload of each type counts.
    entity = _to_driver(row, drivers.documents_of(row.id))
    required = frozenset(settings.get_list("driver.required_documents", []))
    missing = entity.missing_documents(required, on=deps.clock().now().date())

    return ok(
        DriverProfileOut(
            id=row.id, user_id=row.user_id, full_name=user.full_name,
            approval_status=row.approval_status, availability=row.availability,
            rating_average=entity.rating_average, rating_count=row.rating_count,
            completed_trips=row.completed_trips,
            vehicle=VehicleOut.model_validate(vehicle) if vehicle else None,
            missing_documents=sorted(missing),
        ).model_dump()
    )


@router.post("/status")
def set_status(
    body: DriverStatusIn,
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
    vehicle_documents: Annotated[object, Depends(deps.vehicle_documents)],
    settings: Annotated[object, Depends(deps.app_settings)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    """Going online is where approval is enforced.

    An unapproved or suspended driver cannot reach the dispatch pool at all,
    rather than being filtered out of it later (section 28) -- and neither can
    one whose licence or جواز سیر has expired since they were approved.
    """
    from application.use_cases.driver_documents import _to_driver
    from application.use_cases.vehicle_documents import assert_vehicle_papers_current

    row = _driver_of(drivers, actor.user_id)
    # Built with its documents, because approval is not enough on its own: a
    # driver approved in Hamal is still APPROVED in Jadi with a licence that
    # ran out in Saratan. Going online is once a shift, so the read is cheap
    # and it is the last point before a passenger is involved.
    entity = _to_driver(row, drivers.documents_of(row.id))

    if body.availability == DriverAvailability.ONLINE.value:
        entity.go_online()
        entity.assert_documents_current(
            frozenset(settings.get_list("driver.required_documents", [])),
            on=deps.clock().now().date(),
        )
        # Documents do not conjure a car. Without an active vehicle a driver
        # could enter the dispatch pool, be offered a trip, and fail at the
        # moment they accepted it -- in front of a passenger who is already
        # waiting. Refuse here, where it can be explained.
        vehicle = vehicles.current_for_driver(row.id)
        if vehicle is None:
            raise ConflictError(error_codes.VEHICLE_NOT_REGISTERED, driver_id=row.id)
        if vehicle.status != VehicleStatus.ACTIVE.value:
            raise ConflictError(
                error_codes.VEHICLE_SUSPENDED,
                vehicle_id=vehicle.id,
                status=vehicle.status,
            )
        # And the car's own papers, for the same reason as the driver's: the
        # جواز سیر was valid when the vehicle was activated, and that was a
        # moment. This is the one that catches the day it runs out.
        assert_vehicle_papers_current(
            vehicle,
            vehicle_documents.for_vehicle(vehicle.id),
            settings,
            on=deps.clock().now().date(),
        )
    else:
        entity.go_offline()

    row.availability = entity.availability.value
    drivers.save(row)
    audit.write(
        f"driver.went_{body.availability.lower()}",
        actor_id=actor.user_id, actor_role=ActorRole.DRIVER,
        entity_type="driver", entity_id=row.id,
        after={"availability": row.availability},
    )
    return ok({"availability": row.availability})


@router.get("/offers")
def open_offers(
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    offers: Annotated[object, Depends(deps.offers)],
    trips: Annotated[object, Depends(deps.trips)],
) -> dict:
    row = _driver_of(drivers, actor.user_id)
    open_ones = offers.open_for_driver(row.id, at=deps.clock().now())
    return ok(
        [
            {
                "offer_id": o.id,
                "expires_at": o.expires_at.isoformat(),
                "trip": _trip_summary(trips.get(o.trip_id), trips),
            }
            for o in open_ones
        ]
    )


@router.post("/trips/{trip_id}/accept")
@idempotent("driver.accept")
def accept_trip(
    trip_id: str,
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    trips: Annotated[object, Depends(deps.trips)],
    drivers: Annotated[object, Depends(deps.drivers)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
    offers: Annotated[object, Depends(deps.offers)],
    bookings: Annotated[object, Depends(deps.bookings)],
    audit: Annotated[object, Depends(deps.audit)],
    idem: Annotated[object, Depends(deps.idempotency)] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    use_case = AcceptTrip(
        trips=trips, drivers=drivers, vehicles=vehicles, offers=offers,
        bookings=bookings, audit=audit, clock=deps.clock(),
    )
    result = use_case.execute(
        AcceptTripCommand(trip_id=trip_id, driver_user_id=actor.user_id)
    )
    return ok(
        {
            "trip_id": result.trip_id,
            "driver_id": result.driver_id,
            "vehicle_id": result.vehicle_id,
            "status": result.status.value,
        }
    )


@router.post("/trips/{trip_id}/advance")
def advance_trip(
    trip_id: str,
    body: AdvanceTripIn,
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    trips: Annotated[object, Depends(deps.trips)],
    seats: Annotated[object, Depends(deps.seats)],
    bookings: Annotated[object, Depends(deps.bookings)],
    drivers: Annotated[object, Depends(deps.drivers)],
    payments: Annotated[object, Depends(deps.payments)],
    commissions: Annotated[object, Depends(deps.commissions)],
    wallets: Annotated[object, Depends(deps.wallets)],
    settings: Annotated[object, Depends(deps.app_settings)],
    audit: Annotated[object, Depends(deps.audit)],
    notifier: Annotated[object, Depends(deps.notifier)],
    cancellations: Annotated[object, Depends(deps.cancellations)],
) -> dict:
    use_case = AdvanceTrip(
        trips=trips, seats=seats, bookings=bookings, drivers=drivers,
        payments=payments, commissions=commissions, wallets=wallets,
        settings=settings, audit=audit, clock=deps.clock(), new_id=deps.new_id,
        # Without this the cancellation cascade runs silently: the passenger's
        # booking is cancelled and nothing on their phone says so.
        notifier=notifier,
        cancellations=cancellations,
    )
    result = use_case.execute(
        AdvanceTripCommand(
            trip_id=trip_id,
            target=TripStatus(body.target),
            actor_id=actor.user_id,
            actor_role=ActorRole.DRIVER,
            reason_code=body.reason_code or "DRIVER_CANCELLED",
            note=body.note,
        )
    )
    return ok(
        AdvanceTripOut(
            trip_id=result.trip_id, status=result.status.value,
            bookings_advanced=result.bookings_advanced,
            driver_earning=MoneyOut.of(result.driver_earning),
            platform_commission=MoneyOut.of(result.platform_commission),
        ).model_dump()
    )


@router.post("/trips/{trip_id}/verify-passenger")
def verify_passenger(
    trip_id: str,
    body: VerifyPassengerIn,
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    trips: Annotated[object, Depends(deps.trips)],
    bookings: Annotated[object, Depends(deps.bookings)],
    drivers: Annotated[object, Depends(deps.drivers)],
    seats: Annotated[object, Depends(deps.seats)],
    users: Annotated[object, Depends(deps.users)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    use_case = VerifyPassenger(
        trips=trips, bookings=bookings, drivers=drivers, seats=seats,
        users=users, audit=audit, clock=deps.clock(),
    )
    result = use_case.execute(
        VerifyPassengerCommand(
            trip_id=trip_id,
            presented_code=body.code,
            driver_user_id=actor.user_id,
        )
    )
    return ok(
        VerifyPassengerOut(
            booking_id=result.booking_id, number=result.number,
            passenger_name=result.passenger_name, seat_numbers=result.seat_numbers,
            status=result.status.value,
        ).model_dump()
    )


@router.get("/trips/current")
def current_trip(
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    trips: Annotated[object, Depends(deps.trips)],
    bookings: Annotated[object, Depends(deps.bookings)],
    users: Annotated[object, Depends(deps.users)],
) -> dict:
    row = _driver_of(drivers, actor.user_id)
    trip = trips.active_for_driver(row.id)
    if trip is None:
        return ok(None)
    riders = bookings.active_for_trip(trip.id)
    passengers = {
        u.id: u for u in users.get_many([b.passenger_id for b in riders])
    } if riders else {}
    manifest = [
        {
            "booking_id": b.id,
            "number": b.number,
            "status": b.status,
            "seat_count": b.seat_count,
            "pickup_station_id": b.pickup_station_id,
            "dropoff_destination_id": b.dropoff_destination_id,
            # Who he is meeting and what he is collecting. Without these the
            # card showed a trip number, a clock time and a head count, and he
            # could not tell who to look for at the station or how much cash to
            # take -- for a fare he himself agreed.
            "passenger_name": (passengers.get(b.passenger_id) or _none()).full_name,
            # The phone is how two people find each other at a station. Sent
            # only here, on a trip in progress -- never on a receipt from last
            # month, where it would be a directory of everyone he has driven.
            "passenger_phone": (passengers.get(b.passenger_id) or _none()).phone,
            "fare_total_minor": b.fare_total_minor,
            "fare_currency": b.fare_total_currency,
        }
        for b in riders
    ]
    return ok({"trip": _trip_summary(trip, trips), "manifest": manifest})


@router.post("/location")
def ping_location(
    body: LocationPingIn,
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    locations: Annotated[object, Depends(deps.driver_locations)],
    trips: Annotated[object, Depends(deps.trips)],
) -> dict:
    """Deliberately coarse and cheap.

    The cadence is a setting, not a constant, because battery and data cost
    real money to a driver here and the right interval will be found in the
    field rather than guessed now.
    """
    row = _driver_of(drivers, actor.user_id)
    active = trips.active_for_driver(row.id)
    locations.upsert(
        driver_id=row.id,
        latitude=body.latitude,
        longitude=body.longitude,
        heading_degrees=body.heading_degrees,
        accuracy_m=body.accuracy_m,
        trip_id=active.id if active else None,
        recorded_at=body.recorded_at or datetime.now(UTC),
    )
    return ok({"accepted": True})


@router.get("/earnings")
def earnings(
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    wallets: Annotated[object, Depends(deps.wallets)],
) -> dict:
    row = _driver_of(drivers, actor.user_id)
    wallet = wallets.get_or_create(row.id, "AFN")
    return ok(
        EarningsOut(
            available=MoneyOut.of(Money(wallet.available_minor, wallet.currency)),
            pending=MoneyOut.of(Money(wallet.pending_minor, wallet.currency)),
            lifetime_earned=MoneyOut.of(
                Money(wallet.lifetime_earned_minor, wallet.currency)
            ),
            lifetime_commission=MoneyOut.of(
                Money(wallet.lifetime_commission_minor, wallet.currency)
            ),
            lifetime_paid=MoneyOut.of(
                Money(wallet.lifetime_paid_minor, wallet.currency)
            ),
            completed_trips=row.completed_trips,
        ).model_dump()
    )


@router.get("/trips/{trip_id}/map")
def trip_map(
    trip_id: str,
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    trips: Annotated[object, Depends(deps.trips)],
    session: deps.SessionDep,
) -> dict:
    """What the journey looks like drawn, for the screen he stares at en route.

    Everything here degrades honestly. A station that has coordinates gets a
    point; a journey whose two ends both have them gets the road between,
    sliced from the corridor geometry; anything missing is null, and the
    handset decides how much map is worth showing. The stations list is the
    driver's whole coordinate-bearing world -- a handful of dots that make a
    valley recognisable at a glance.
    """
    from sqlalchemy import text as sql

    driver = _driver_of(drivers, actor.user_id)
    trip = trips.get(trip_id)
    if trip.driver_id != driver.id:
        # Not "forbidden": another driver's trip should not even be shown to
        # exist. The same shape a wrong id gets.
        raise NotFoundError(trips.not_found_code, trip_id=trip_id)

    origin, origin_code = mapdata.place(session, "stations", trip.origin_station_id)
    destination, dest_code = mapdata.place(session, "destinations", trip.destination_id)

    shape = mapdata.journey_line(
        origin_code,
        dest_code,
        (origin["longitude"], origin["latitude"]) if origin else None,
        (destination["longitude"], destination["latitude"]) if destination else None,
    )

    stations = [
        {"name": name, "latitude": float(lat), "longitude": float(lon)}
        for name, lat, lon in session.execute(sql(
            "SELECT name, latitude, longitude FROM stations "
            "WHERE latitude IS NOT NULL AND deleted_at IS NULL AND status = 'ACTIVE'"
        ))
    ]

    # The road's advisories: bends found by the curvature scan, hand-placed
    # caution stretches, and the bazaars -- which are simply the stations
    # whose name says so. The handset announces each as he enters it; the
    # server just knows where they are.
    alerts = list(mapdata.road_alerts())
    for name, lat, lon in session.execute(sql(
        "SELECT name, latitude, longitude FROM stations "
        "WHERE latitude IS NOT NULL AND deleted_at IS NULL "
        "AND status = 'ACTIVE' AND name LIKE '%بازار%'"
    )):
        alerts.append({
            "latitude": float(lat), "longitude": float(lon), "radius_m": 400,
            "kind": "bazaar", "message_key": "road.alert.bazaar",
        })

    return ok({
        "origin": origin,
        "destination": destination,
        # (lat, lon) pairs, the order every mobile mapping API speaks.
        "geometry": [[lat, lon] for lon, lat in shape["points"]] if shape else None,
        "avg_speed_kmh": shape["avg_speed_kmh"] if shape else None,
        "stations": stations,
        "alerts": alerts,
        "attribution": "© OpenStreetMap",
    })


def _driver_of(drivers, user_id: str):
    row = drivers.find_by_user(user_id)
    if row is None:
        raise NotFoundError(error_codes.DRIVER_NOT_FOUND, user_id=user_id)
    return row


def _trip_summary(trip, trips) -> dict:
    available = trips.seats_available_map([trip.id]).get(trip.id, 0)
    origin, destination = trips.place_names([trip.id]).get(trip.id, (None, None))
    return TripSummaryOut(
        id=trip.id, number=trip.number, status=trip.status, ride_kind=trip.ride_kind,
        scheduled_departure_at=trip.scheduled_departure_at,
        origin_station_id=trip.origin_station_id, origin_station_name=origin,
        destination_id=trip.destination_id, destination_name=destination,
        seat_capacity=trip.seat_capacity, seats_available=available,
        driver_id=trip.driver_id, vehicle_id=trip.vehicle_id,
    ).model_dump()


class _Missing:
    """A passenger row that is not there. Keeps the manifest a list of dicts
    with the same keys rather than one that sometimes omits them."""

    full_name = None
    phone = None


def _none() -> _Missing:
    return _Missing()
