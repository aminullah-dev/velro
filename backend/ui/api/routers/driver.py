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
from domain.driver import Driver
from domain.enums import (
    ActorRole,
    DriverApprovalStatus,
    DriverAvailability,
    TripStatus,
)
from shared import error_codes
from shared.errors import NotFoundError
from shared.money import Money
from ui.api import deps
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
    row = _driver_of(drivers, actor.user_id)
    user = users.get(row.user_id)
    vehicle = vehicles.primary_for_driver(row.id)

    entity = Driver(
        id=row.id, user_id=row.user_id,
        approval_status=DriverApprovalStatus(row.approval_status),
        availability=DriverAvailability(row.availability),
        rating_sum=row.rating_sum, rating_count=row.rating_count,
    )
    required = frozenset(settings.get_list("driver.required_documents", []))
    held = {
        d.document_type_code for d in drivers.documents_of(row.id) if d.status == "VERIFIED"
    }
    return ok(
        DriverProfileOut(
            id=row.id, user_id=row.user_id, full_name=user.full_name,
            approval_status=row.approval_status, availability=row.availability,
            rating_average=entity.rating_average, rating_count=row.rating_count,
            completed_trips=row.completed_trips,
            vehicle=VehicleOut.model_validate(vehicle) if vehicle else None,
            missing_documents=sorted(required - held),
        ).model_dump()
    )


@router.post("/status")
def set_status(
    body: DriverStatusIn,
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    """Going online is where approval is enforced.

    An unapproved or suspended driver cannot reach the dispatch pool at all,
    rather than being filtered out of it later (section 28).
    """
    row = _driver_of(drivers, actor.user_id)
    entity = Driver(
        id=row.id, user_id=row.user_id,
        approval_status=DriverApprovalStatus(row.approval_status),
        availability=DriverAvailability(row.availability),
    )
    if body.availability == DriverAvailability.ONLINE.value:
        entity.go_online()
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
) -> dict:
    use_case = AdvanceTrip(
        trips=trips, seats=seats, bookings=bookings, drivers=drivers,
        payments=payments, commissions=commissions, wallets=wallets,
        settings=settings, audit=audit, clock=deps.clock(), new_id=deps.new_id,
    )
    result = use_case.execute(
        AdvanceTripCommand(
            trip_id=trip_id,
            target=TripStatus(body.target),
            actor_id=actor.user_id,
            actor_role=ActorRole.DRIVER,
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
) -> dict:
    row = _driver_of(drivers, actor.user_id)
    trip = trips.active_for_driver(row.id)
    if trip is None:
        return ok(None)
    manifest = [
        {
            "booking_id": b.id,
            "number": b.number,
            "status": b.status,
            "seat_count": b.seat_count,
            "pickup_station_id": b.pickup_station_id,
            "dropoff_destination_id": b.dropoff_destination_id,
        }
        for b in bookings.active_for_trip(trip.id)
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
            completed_trips=row.completed_trips,
        ).model_dump()
    )


def _driver_of(drivers, user_id: str):
    row = drivers.find_by_user(user_id)
    if row is None:
        raise NotFoundError(error_codes.DRIVER_NOT_FOUND, user_id=user_id)
    return row


def _trip_summary(trip, trips) -> dict:
    available = trips.seats_available_map([trip.id]).get(trip.id, 0)
    return TripSummaryOut(
        id=trip.id, number=trip.number, status=trip.status, ride_kind=trip.ride_kind,
        scheduled_departure_at=trip.scheduled_departure_at,
        origin_station_id=trip.origin_station_id, destination_id=trip.destination_id,
        seat_capacity=trip.seat_capacity, seats_available=available,
        driver_id=trip.driver_id, vehicle_id=trip.vehicle_id,
    ).model_dump()
