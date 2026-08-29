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
from domain.enums import PaymentMethod, RideKind
from shared import error_codes
from shared.errors import PermissionError
from shared.money import Money
from ui.api import deps
from ui.api.errors import ok
from ui.api.idempotency import idempotent
from ui.api.schemas.booking import (
    BookingOut,
    BookSeatsIn,
    CancelBookingIn,
    CancelBookingOut,
    RateTripIn,
    RateTripOut,
    SearchTripsIn,
    TripOptionOut,
)
from ui.api.schemas.common import MoneyOut

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
    fare_strategy: Annotated[object, Depends(deps.fare_strategy)],
    numbers: Annotated[object, Depends(deps.numbers)],
    codes: Annotated[object, Depends(deps.verification_codes)],
    settings: Annotated[object, Depends(deps.app_settings)],
    audit: Annotated[object, Depends(deps.audit)],
    idem: Annotated[object, Depends(deps.idempotency)] = None,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
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
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    rows = bookings.list_for_passenger(actor.user_id, limit=limit, offset=offset)
    return ok(
        [
            _booking_out(r, [s.seat_number for s in bookings.seats_of(r.id)], reveal_code=True)
            for r in rows
        ]
    )


@router.get("/bookings/{booking_id}")
def get_booking(
    booking_id: str,
    actor: deps.ActorDep,
    bookings: Annotated[object, Depends(deps.bookings)],
) -> dict:
    row = bookings.get(booking_id)
    if row.passenger_id != actor.user_id and not actor.is_staff:
        raise PermissionError(error_codes.PERMISSION_DENIED, booking_id=booking_id)
    seat_numbers = [s.seat_number for s in bookings.seats_of(row.id)]
    return ok(_booking_out(row, seat_numbers, reveal_code=row.passenger_id == actor.user_id))


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
) -> dict:
    use_case = CancelBooking(
        bookings=bookings, trips=trips, seats=seats, cancellations=cancellations,
        settings=settings, audit=audit, clock=deps.clock(), new_id=deps.new_id,
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


def _booking_out(row, seat_numbers: list[int], *, reveal_code: bool) -> dict:
    return BookingOut(
        id=row.id, number=row.number, trip_id=row.trip_id, status=row.status,
        ride_kind=row.ride_kind, seat_count=row.seat_count, seat_numbers=seat_numbers,
        pickup_station_id=row.pickup_station_id,
        dropoff_destination_id=row.dropoff_destination_id,
        fare_total=MoneyOut.of(Money(row.fare_total_minor, row.fare_total_currency)),
        payment_method=row.payment_method,
        # The code boards a passenger. Only its owner ever sees it.
        verification_code=row.verification_code if reveal_code else None,
        created_at=row.created_at,
    ).model_dump()
