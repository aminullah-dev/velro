"""Ratings, both directions.

A rating is only meaningful once the trip is over, and only from someone who
was on it. Both are checked here rather than trusted from the client.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.enums import ActorRole, BookingStatus, TripStatus
from shared import error_codes
from shared.errors import ConflictError, PermissionError, ValidationError


@dataclass(frozen=True, slots=True)
class RateTripCommand:
    trip_id: str
    rater_user_id: str
    score: int
    comment: str | None = None
    booking_id: str | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class RateTripResult:
    rating_id: str
    ratee_user_id: str
    score: int


class RateTrip:
    def __init__(self, *, trips, bookings, drivers, ratings, users, audit, clock, new_id) -> None:
        self._trips = trips
        self._bookings = bookings
        self._drivers = drivers
        self._ratings = ratings
        self._users = users
        self._audit = audit
        self._clock = clock
        self._new_id = new_id

    def execute(self, cmd: RateTripCommand) -> RateTripResult:
        if not 1 <= cmd.score <= 5:
            raise ValidationError(error_codes.RATING_OUT_OF_RANGE, score=cmd.score)

        trip = self._trips.get(cmd.trip_id)
        if trip.status != TripStatus.COMPLETED.value:
            raise ConflictError(
                error_codes.RATING_TRIP_NOT_COMPLETED,
                trip_id=trip.id,
                status=trip.status,
            )

        ratee_id, rater_role = self._resolve_parties(trip, cmd)

        if self._ratings.find(trip.id, cmd.rater_user_id, ratee_id) is not None:
            raise ConflictError(
                error_codes.RATING_ALREADY_SUBMITTED,
                trip_id=trip.id,
                rater_user_id=cmd.rater_user_id,
            )

        rating_id = self._new_id()
        self._ratings.create(
            id=rating_id,
            trip_id=trip.id,
            booking_id=cmd.booking_id,
            rater_user_id=cmd.rater_user_id,
            ratee_user_id=ratee_id,
            rater_role=rater_role.value,
            score=cmd.score,
            comment=cmd.comment,
        )

        # Running averages live as sum and count on the row of whoever was
        # rated, so they can be corrected exactly rather than drifting.
        #
        # Both directions are recorded now. The rating row for a driver rating
        # a passenger has been written since this file existed -- rater_role
        # says which way it went -- but nothing added it up, so the score a
        # driver gave was stored and never became anything.
        if rater_role is ActorRole.PASSENGER and trip.driver_id:
            self._drivers.record_rating(trip.driver_id, cmd.score)
        elif rater_role is ActorRole.DRIVER:
            self._users.record_rating(ratee_id, cmd.score)

        self._audit.write(
            "rating.submitted",
            actor_id=cmd.rater_user_id,
            actor_role=rater_role,
            entity_type="trip",
            entity_id=trip.id,
            after={"score": cmd.score, "ratee_user_id": ratee_id},
            request_id=cmd.request_id,
        )
        return RateTripResult(rating_id=rating_id, ratee_user_id=ratee_id, score=cmd.score)

    def _resolve_parties(self, trip, cmd: RateTripCommand) -> tuple[str, ActorRole]:
        """Work out who is rating whom, and refuse anyone who was not aboard."""
        driver = self._drivers.get(trip.driver_id) if trip.driver_id else None

        if driver is not None and driver.user_id == cmd.rater_user_id:
            # Driver rating a passenger: which one must be stated.
            if cmd.booking_id is None:
                raise ValidationError(
                    error_codes.VALIDATION_FAILED, field="booking_id", trip_id=trip.id
                )
            booking = self._bookings.get(cmd.booking_id)
            if booking.trip_id != trip.id:
                raise PermissionError(
                    error_codes.PERMISSION_DENIED, booking_id=cmd.booking_id, trip_id=trip.id
                )
            return booking.passenger_id, ActorRole.DRIVER

        # Passenger rating the driver: they must have actually travelled.
        travelled = [
            b for b in self._bookings.list_for_trip(trip.id)
            if b.passenger_id == cmd.rater_user_id
            and b.status == BookingStatus.COMPLETED.value
        ]
        if not travelled:
            raise PermissionError(
                error_codes.PERMISSION_DENIED, trip_id=trip.id, actor_id=cmd.rater_user_id
            )
        if driver is None:
            raise ConflictError(error_codes.DRIVER_NOT_FOUND, trip_id=trip.id)
        return driver.user_id, ActorRole.PASSENGER
