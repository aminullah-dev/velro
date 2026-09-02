"""Passenger search and booking."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query

from application.use_cases.book_seats import BookSeats, BookSeatsCommand
from application.use_cases.cancel_booking import CancelBooking, CancelBookingCommand
from application.use_cases.rate_trip import RateTrip, RateTripCommand
from application.use_cases.search_trips import SearchTrips, SearchTripsQuery
from domain.enums import BookingStatus, PaymentMethod, RideKind
from domain.lifecycles import BOOKING_LIFECYCLE
from shared import error_codes
from shared.errors import NotFoundError, PermissionError
from shared.money import Money
from ui.api import deps
from ui.api.errors import ok
from ui.api.geofence import assert_inside
from ui.api.idempotency import idempotent
from ui.api.schemas.booking import (
    BookingOut,
    BookSeatsIn,
    CancelBookingIn,
    CancelBookingOut,
    FareComponentOut,
    RateTripIn,
    RateTripOut,
    SearchTripsIn,
    TripOptionOut,
)
from ui.api.schemas.common import MoneyOut

# What "upcoming" and "past" mean, in one place. A booking the passenger can
# still act on is upcoming; everything else is history.
_SCOPES: dict[str, list[str] | None] = {
    "all": None,
    "upcoming": [
        BookingStatus.PENDING.value,
        BookingStatus.CONFIRMED.value,
        BookingStatus.DRIVER_ASSIGNED.value,
        BookingStatus.READY.value,
        BookingStatus.ONBOARD.value,
    ],
    "past": [
        BookingStatus.COMPLETED.value,
        BookingStatus.CANCELLED.value,
        BookingStatus.NO_SHOW.value,
    ],
}

router = APIRouter(tags=["bookings"])


@router.post("/trips/search")
def search_trips(
    body: SearchTripsIn,
    routes: Annotated[object, Depends(deps.routes)],
    trips: Annotated[object, Depends(deps.trips)],
    geo: Annotated[object, Depends(deps.geography)],
    fare_strategy: Annotated[object, Depends(deps.fare_strategy)],
    settings: Annotated[object, Depends(deps.app_settings)],
) -> dict:
    use_case = SearchTrips(
        routes=routes, trips=trips, geography=geo,
        fare_strategy=fare_strategy, settings=settings, clock=deps.clock(),
    )
    options = use_case.execute(
        SearchTripsQuery(
            origin_station_id=body.origin_station_id,
            destination_id=body.destination_id,
            departure_after=body.departure_after or datetime.now(UTC),
            seat_count=body.seat_count,
            ride_kind=RideKind(body.ride_kind) if body.ride_kind else None,
        )
    )
    return ok(
        [
            TripOptionOut(
                trip_id=o.trip_id, number=o.number, route_id=o.route_id,
                ride_kind=o.ride_kind.value,
                scheduled_departure_at=o.scheduled_departure_at,
                seats_available=o.seats_available, seat_capacity=o.seat_capacity,
                fare_total=MoneyOut.of(o.fare_total),
                fare_per_seat=MoneyOut.of(o.fare_per_seat),
                status=o.status.value, has_driver=o.driver_id is not None,
                distance_m=o.distance_m, duration_minutes=o.duration_minutes,
            ).model_dump()
            for o in options
        ],
        meta={"count": len(options)},
    )


@router.post("/bookings")
@idempotent("bookings.create")
def create_booking(
    body: BookSeatsIn,
    actor: deps.ActorDep,
    trips: Annotated[object, Depends(deps.trips)],
    seats: Annotated[object, Depends(deps.seats)],
    bookings: Annotated[object, Depends(deps.bookings)],
    routes: Annotated[object, Depends(deps.routes)],
    geo: Annotated[object, Depends(deps.geography)],
    fare_strategy: Annotated[object, Depends(deps.fare_strategy)],
    numbers: Annotated[object, Depends(deps.numbers)],
    codes: Annotated[object, Depends(deps.verification_codes)],
    settings: Annotated[object, Depends(deps.app_settings)],
    audit: Annotated[object, Depends(deps.audit)],
    idem: Annotated[object, Depends(deps.idempotency)] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    # A booking summons a driver to a station just as surely as an ask does,
    # so it passes the same fence. A refusal raises before store.remember runs,
    # so it is never cached against the key -- the same attempt, retried after
    # walking into the service area, gets a fresh verdict.
    assert_inside(
        geo=geo,
        app_settings=settings,
        exempt_phones=deps.settings().geofence_exempt_phones,
        phone=deps.users(trips.session).get(actor.user_id).phone,
        latitude=body.latitude,
        longitude=body.longitude,
        is_mock=body.location_is_mock,
    )

    use_case = BookSeats(
        trips=trips, seats=seats, bookings=bookings, routes=routes,
        fare_strategy=fare_strategy, numbers=numbers, codes=codes,
        settings=settings, audit=audit, clock=deps.clock(), new_id=deps.new_id,
    )
    result = use_case.execute(
        BookSeatsCommand(
            trip_id=body.trip_id,
            passenger_id=actor.user_id,
            seat_count=body.seat_count,
            pickup_station_id=body.pickup_station_id,
            dropoff_destination_id=body.dropoff_destination_id,
            payment_method=PaymentMethod(body.payment_method),
            passenger_note=body.passenger_note,
        )
    )
    row = bookings.get(result.booking_id)
    return ok(_booking_out(row, result.seat_numbers, reveal_code=True))


@router.get("/bookings")
def list_bookings(
    actor: deps.ActorDep,
    bookings: Annotated[object, Depends(deps.bookings)],
    trips: Annotated[object, Depends(deps.trips)],
    drivers: Annotated[object, Depends(deps.drivers)],
    users: Annotated[object, Depends(deps.users)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
    cancellations: Annotated[object, Depends(deps.cancellations)],
    stations: Annotated[object, Depends(deps.stations_repo)],
    destinations: Annotated[object, Depends(deps.destinations_repo)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    scope: Annotated[str, Query(pattern=r"^(all|upcoming|past)$")] = "all",
) -> dict:
    """The passenger's own bookings, section 73.

    ``scope`` splits the list the way a passenger thinks about it: a journey
    still to come, which they may need to cancel or board, and one already
    finished, which they only want a record of.
    """
    statuses = _SCOPES.get(scope)
    # One extra row decides whether there is another page, without a count
    # query over a table that only grows.
    rows = bookings.list_for_passenger(
        actor.user_id, limit=limit + 1, offset=offset, statuses=statuses
    )
    page, has_more = rows[:limit], len(rows) > limit

    enricher = _Enricher(
        trips=trips, drivers=drivers, users=users,
        vehicles=vehicles, cancellations=cancellations,
        stations=stations, destinations=destinations,
    )
    extra = enricher.for_bookings(page)
    seats = bookings.seats_for_bookings([r.id for r in page])
    return ok(
        {
            "bookings": [
                _booking_out(
                    r,
                    sorted(seats.get(r.id, [])),
                    reveal_code=True,
                    **extra.get(r.id, {}),
                )
                for r in page
            ],
            "has_more": has_more,
            "next_offset": offset + len(page),
        }
    )


@router.get("/bookings/{booking_id}")
def get_booking(
    booking_id: str,
    actor: deps.ActorDep,
    bookings: Annotated[object, Depends(deps.bookings)],
    trips: Annotated[object, Depends(deps.trips)],
    drivers: Annotated[object, Depends(deps.drivers)],
    users: Annotated[object, Depends(deps.users)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
    cancellations: Annotated[object, Depends(deps.cancellations)],
    stations: Annotated[object, Depends(deps.stations_repo)],
    destinations: Annotated[object, Depends(deps.destinations_repo)],
) -> dict:
    row = bookings.get(booking_id)
    if row.passenger_id != actor.user_id and not actor.is_staff:
        raise PermissionError(error_codes.PERMISSION_DENIED, booking_id=booking_id)
    seat_numbers = [s.seat_number for s in bookings.seats_of(row.id)]
    enricher = _Enricher(
        trips=trips, drivers=drivers, users=users,
        vehicles=vehicles, cancellations=cancellations,
        stations=stations, destinations=destinations,
    )
    extra = enricher.for_bookings([row]).get(row.id, {})
    return ok(
        _booking_out(
            row,
            seat_numbers,
            reveal_code=row.passenger_id == actor.user_id,
            **extra,
        )
    )


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(
    booking_id: str,
    body: CancelBookingIn,
    actor: deps.ActorDep,
    bookings: Annotated[object, Depends(deps.bookings)],
    trips: Annotated[object, Depends(deps.trips)],
    seats: Annotated[object, Depends(deps.seats)],
    cancellations: Annotated[object, Depends(deps.cancellations)],
    settings: Annotated[object, Depends(deps.app_settings)],
    audit: Annotated[object, Depends(deps.audit)],
    drivers: Annotated[object, Depends(deps.drivers)],
) -> dict:
    use_case = CancelBooking(
        bookings=bookings, trips=trips, seats=seats, cancellations=cancellations,
        settings=settings, audit=audit, clock=deps.clock(), new_id=deps.new_id,
        drivers=drivers,
    )
    result = use_case.execute(
        CancelBookingCommand(
            booking_id=booking_id,
            actor_id=actor.user_id,
            actor_role=actor.role,
            reason_code=body.reason_code,
            note=body.note,
        )
    )
    return ok(
        CancelBookingOut(
            booking_id=result.booking_id,
            status=result.status.value,
            seats_released=result.seats_released,
            fee=MoneyOut.of(result.fee),
        ).model_dump()
    )


@router.post("/trips/{trip_id}/rating")
def rate_trip(
    trip_id: str,
    body: RateTripIn,
    actor: deps.ActorDep,
    trips: Annotated[object, Depends(deps.trips)],
    bookings: Annotated[object, Depends(deps.bookings)],
    drivers: Annotated[object, Depends(deps.drivers)],
    ratings: Annotated[object, Depends(deps.ratings)],
    users: Annotated[object, Depends(deps.users)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    use_case = RateTrip(
        trips=trips, bookings=bookings, drivers=drivers, ratings=ratings,
        users=users, audit=audit, clock=deps.clock(), new_id=deps.new_id,
    )
    result = use_case.execute(
        RateTripCommand(
            trip_id=trip_id,
            rater_user_id=actor.user_id,
            score=body.score,
            comment=body.comment,
            booking_id=body.booking_id,
        )
    )
    return ok(RateTripOut(**asdict(result)).model_dump())


def _booking_out(
    row,
    seat_numbers: list[int],
    *,
    reveal_code: bool,
    trip=None,
    driver_name: str | None = None,
    driver_phone: str | None = None,
    vehicle=None,
    cancellation=None,
    pickup_name: str | None = None,
    dropoff_name: str | None = None,
) -> dict:
    """One booking, as much of a receipt as is known.

    Everything beyond the booking itself is optional: a booking made a minute
    ago has no driver and no departure, and a screen rendering it must show what
    exists rather than wait for a complete record that will never arrive.
    """
    return BookingOut(
        id=row.id, number=row.number, trip_id=row.trip_id, status=row.status,
        trip_number=trip.number if trip else None,
        ride_kind=row.ride_kind, seat_count=row.seat_count, seat_numbers=seat_numbers,
        pickup_station_id=row.pickup_station_id,
        dropoff_destination_id=row.dropoff_destination_id,
        pickup_station_name=pickup_name,
        dropoff_destination_name=dropoff_name,
        fare_total=MoneyOut.of(Money(row.fare_total_minor, row.fare_total_currency)),
        fare_breakdown=[
            FareComponentOut(
                key=str(c.get("key", "fare.component.other")),
                amount=MoneyOut.of(
                    Money(
                        int(c.get("amount_minor", 0)),
                        str(c.get("currency", row.fare_total_currency)),
                    )
                ),
                quantity=int(c.get("quantity", 1)),
            )
            for c in (row.fare_breakdown or [])
        ],
        payment_method=row.payment_method,
        scheduled_departure_at=trip.scheduled_departure_at if trip else None,
        return_for=trip.return_for if trip else None,
        driver_name=driver_name,
        # Only while the journey is still ahead of her. BOOKING_LIFECYCLE knows
        # which those are, so this cannot drift from the definition of "over".
        driver_phone=(
            driver_phone
            if not BOOKING_LIFECYCLE.is_terminal(BookingStatus(row.status))
            else None
        ),
        vehicle_plate=vehicle.plate_number if vehicle else None,
        vehicle_description=_vehicle_description(vehicle),
        confirmed_at=row.confirmed_at,
        boarded_at=row.boarded_at,
        completed_at=row.completed_at,
        cancelled_at=row.cancelled_at,
        cancellation_reason_code=cancellation.reason_code if cancellation else None,
        cancellation_fee=(
            MoneyOut.of(Money(cancellation.fee_minor, cancellation.fee_currency))
            if cancellation
            else None
        ),
        # The code boards a passenger. Only its owner ever sees it.
        verification_code=row.verification_code if reveal_code else None,
        created_at=row.created_at,
    ).model_dump()


def _vehicle_description(vehicle) -> str | None:
    """"Toyota Corolla 2012", skipping whatever the driver did not record."""
    if vehicle is None:
        return None
    parts = [vehicle.brand, vehicle.model, str(vehicle.year) if vehicle.year else None]
    described = " ".join(p for p in parts if p)
    return described or None


class _Enricher:
    """Resolves the trip, driver and vehicle for a page of bookings.

    Built once per request and fed every booking at once: a history screen
    showing twenty bookings would otherwise issue sixty extra queries, on a
    connection where each one is felt.
    """

    def __init__(
        self, *, trips, drivers, users, vehicles, cancellations, stations, destinations
    ) -> None:
        self._trips = trips
        self._drivers = drivers
        self._users = users
        self._vehicles = vehicles
        self._cancellations = cancellations
        self._stations = stations
        self._destinations = destinations

    def for_bookings(self, rows: list) -> dict[str, dict]:
        trip_ids = {r.trip_id for r in rows}
        trips = {t.id: t for t in self._trips.by_ids(trip_ids)} if trip_ids else {}

        driver_ids = {t.driver_id for t in trips.values() if t.driver_id}
        drivers = {d.id: d for d in self._drivers.by_ids(driver_ids)} if driver_ids else {}
        user_ids = {d.user_id for d in drivers.values()}
        users = {u.id: u for u in self._users.by_ids(user_ids)} if user_ids else {}

        vehicle_ids = {t.vehicle_id for t in trips.values() if t.vehicle_id}
        vehicles = (
            {v.id: v for v in self._vehicles.by_ids(vehicle_ids)} if vehicle_ids else {}
        )

        # Only cancelled bookings have a cancellation, so the lookup is scoped
        # to them rather than run for every row.
        cancelled = [r.id for r in rows if r.status == BookingStatus.CANCELLED.value]
        cancellations = (
            {c.booking_id: c for c in self._cancellations.by_booking_ids(cancelled)}
            if cancelled
            else {}
        )

        stations = {
            s.id: s for s in self._stations.by_ids({r.pickup_station_id for r in rows})
        }
        destinations = {
            d.id: d
            for d in self._destinations.by_ids({r.dropoff_destination_id for r in rows})
        }

        out: dict[str, dict] = {}
        for row in rows:
            trip = trips.get(row.trip_id)
            driver = drivers.get(trip.driver_id) if trip and trip.driver_id else None
            user = users.get(driver.user_id) if driver else None
            out[row.id] = {
                "trip": trip,
                "driver_name": user.full_name if user else None,
                "driver_phone": user.phone if user else None,
                "vehicle": vehicles.get(trip.vehicle_id) if trip and trip.vehicle_id else None,
                "cancellation": cancellations.get(row.id),
                "pickup_name": getattr(stations.get(row.pickup_station_id), "name", None),
                "dropoff_name": getattr(
                    destinations.get(row.dropoff_destination_id), "name", None
                ),
            }
        return out

#: A passenger may watch the car only while their booking is riding on it.
_TRACKABLE_STATUSES = frozenset({"DRIVER_ASSIGNED", "READY", "ONBOARD"})


@router.get("/bookings/{booking_id}/vehicle-location")
def vehicle_location(
    booking_id: str,
    actor: deps.ActorDep,
    bookings: Annotated[object, Depends(deps.bookings)],
    trips: Annotated[object, Depends(deps.trips)],
    drivers: Annotated[object, Depends(deps.drivers)],
    locations: Annotated[object, Depends(deps.driver_locations)],
) -> dict:
    """Where the car is, for the person waiting at the station for it.

    The same privacy shape as the driver's photograph: not a role, a live
    connection. Only the booking's own passenger, only while the booking is
    assigned to a car and not yet finished, and only a ping recorded during
    THIS trip -- a stale ping from yesterday would draw the car at the
    driver's house, which is a lie about the trip and a disclosure about the
    driver. Null means "nothing honest to show", and the screen says nothing.
    """
    booking = bookings.get(booking_id)
    if booking.passenger_id != actor.user_id:
        raise NotFoundError(bookings.not_found_code, booking_id=booking_id)
    if booking.status not in _TRACKABLE_STATUSES or booking.trip_id is None:
        return ok(None)

    trip = trips.find(booking.trip_id)
    if trip is None or trip.driver_id is None:
        return ok(None)
    ping = locations.find(trip.driver_id)
    if ping is None or ping.trip_id != trip.id:
        return ok(None)

    age_s = max(0, int((datetime.now(UTC) - ping.recorded_at).total_seconds()))
    return ok({
        "latitude": float(ping.latitude),
        "longitude": float(ping.longitude),
        "heading_degrees": ping.heading_degrees,
        "recorded_at": ping.recorded_at.isoformat(),
        "age_seconds": age_s,
    })

@router.get("/bookings/{booking_id}/driver")
def booking_driver(
    booking_id: str,
    actor: deps.ActorDep,
    bookings: Annotated[object, Depends(deps.bookings)],
    trips: Annotated[object, Depends(deps.trips)],
    drivers: Annotated[object, Depends(deps.drivers)],
    users: Annotated[object, Depends(deps.users)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
) -> dict:
    """Who is coming for me, and in what.

    The tracking screen's second half: a passenger waiting at a roadside
    deserves the driver's name, his standing, the car's plate to check
    against the one that stops, and a number to call -- there is no chat
    system and no masking proxy in this product's world; a phone call is
    how a driver and a passenger have always found each other here, and
    the driver already holds her number in his manifest for exactly the
    same reason.

    Same privacy shape as the photograph and the moving dot: her own
    booking, and only while a car is actually owed. Null before a driver
    is assigned and after the ride is over -- yesterday's driver is not
    hers to call.
    """
    booking = bookings.get(booking_id)
    if booking.passenger_id != actor.user_id:
        raise NotFoundError(bookings.not_found_code, booking_id=booking_id)
    if booking.status not in _TRACKABLE_STATUSES or booking.trip_id is None:
        return ok(None)
    trip = trips.find(booking.trip_id)
    if trip is None or trip.driver_id is None:
        return ok(None)

    driver = drivers.get(trip.driver_id)
    user = users.get(driver.user_id)
    vehicle = vehicles.find(trip.vehicle_id) if trip.vehicle_id else None
    return ok({
        "driver_id": driver.id,
        "name": user.full_name,
        "phone": user.phone,
        "rating_average": (
            round(driver.rating_sum / driver.rating_count, 2)
            if driver.rating_count else None
        ),
        "rating_count": driver.rating_count,
        "vehicle": {
            "brand": vehicle.brand,
            "model": vehicle.model,
            "colour": vehicle.colour,
            "plate_number": vehicle.plate_number,
            "seat_capacity": vehicle.seat_capacity,
        } if vehicle else None,
    })

