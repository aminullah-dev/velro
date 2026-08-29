"""Trip search.

The passenger's first screen after choosing where and when. It runs on a slow
connection, so it is one bounded query for trips plus one grouped query for
availability -- never one availability query per result.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from application.pricing.fixed import FareRequest
from domain.enums import RideKind, TripStatus
from shared import error_codes
from shared.errors import NotFoundError
from shared.money import Money


@dataclass(frozen=True, slots=True)
class SearchTripsQuery:
    origin_station_id: str
    destination_id: str
    departure_after: datetime
    seat_count: int = 1
    ride_kind: RideKind | None = None
    window_hours: int | None = None


@dataclass(frozen=True, slots=True)
class TripOption:
    trip_id: str
    number: str
    route_id: str
    ride_kind: RideKind
    scheduled_departure_at: datetime
    seats_available: int
    seat_capacity: int
    fare_total: Money | None
    fare_per_seat: Money | None
    status: TripStatus
    driver_id: str | None
    vehicle_id: str | None
    pickup_sequence: int
    dropoff_sequence: int


class SearchTrips:
    def __init__(
        self, *, routes, trips, geography, fare_strategy, settings, clock
    ) -> None:
        self._routes = routes
        self._trips = trips
        self._geography = geography
        self._fares = fare_strategy
        self._settings = settings
        self._clock = clock

    def execute(self, query: SearchTripsQuery) -> list[TripOption]:
        station = self._geography.get_station(query.origin_station_id)
        destination = self._geography.get_destination(query.destination_id)
        if station.status != "ACTIVE":
            raise NotFoundError(error_codes.STATION_DISABLED, station_id=station.id)
        if destination.status != "ACTIVE":
            raise NotFoundError(
                error_codes.DESTINATION_DISABLED, destination_id=destination.id
            )

        serving = self._routes.find_serving(station.id, destination.id)
        if not serving:
            # No route means no vehicle goes there -- a clearer answer than an
            # empty list, and the client can say so in words.
            raise NotFoundError(
                error_codes.ROUTE_NOT_RESOLVABLE,
                origin=station.id,
                destination=destination.id,
            )

        window = query.window_hours or self._settings.get_int("trip.search_window_hours", 12)
        found = self._trips.search(
            route_ids=[r.id for r in serving],
            departure_from=query.departure_after,
            departure_to=query.departure_after + timedelta(hours=window),
            ride_kind=query.ride_kind.value if query.ride_kind else None,
            limit=50,
        )
        if not found:
            return []

        # One grouped query for every result, rather than N+1.
        availability = self._trips.seats_available_map([t.id for t in found])
        segments = {
            route.id: self._segment_for(route.id, station.id, destination.id)
            for route in serving
        }

        options: list[TripOption] = []
        for trip in found:
            seats_free = availability.get(trip.id, 0)
            if seats_free < query.seat_count:
                continue
            segment = segments.get(trip.route_id)
            if segment is None:
                continue
            from_seq, to_seq = segment

            fare_total = fare_per_seat = None
            try:
                quote = self._fares.quote(
                    FareRequest(
                        route_id=trip.route_id,
                        ride_kind=RideKind(trip.ride_kind),
                        from_sequence=from_seq,
                        to_sequence=to_seq,
                        seat_count=query.seat_count,
                        on=query.departure_after.date(),
                    )
                )
                fare_total = quote.total()
                fare_per_seat = quote.per_seat()
            except NotFoundError:
                # A route with no configured price is shown without one rather
                # than hidden: an operator needs to see that the gap exists.
                pass

            options.append(
                TripOption(
                    trip_id=trip.id,
                    number=trip.number,
                    route_id=trip.route_id,
                    ride_kind=RideKind(trip.ride_kind),
                    scheduled_departure_at=trip.scheduled_departure_at,
                    seats_available=seats_free,
                    seat_capacity=trip.seat_capacity,
                    fare_total=fare_total,
                    fare_per_seat=fare_per_seat,
                    status=TripStatus(trip.status),
                    driver_id=trip.driver_id,
                    vehicle_id=trip.vehicle_id,
                    pickup_sequence=from_seq,
                    dropoff_sequence=to_seq,
                )
            )
        return options

    def _segment_for(
        self, route_id: str, station_id: str, destination_id: str
    ) -> tuple[int, int] | None:
        stops = {
            (s.station_id or s.destination_id): (s.sequence, s.is_pickup, s.is_dropoff)
            for s in self._routes.stops_of(route_id)
        }
        origin = stops.get(station_id)
        target = stops.get(destination_id)
        if not origin or not target or origin[0] >= target[0]:
            return None
        if not origin[1] or not target[2]:
            return None
        return origin[0], target[0]


def today_in(tz_name: str, now: datetime) -> date:
    """A 'day' is a business-day range in the product's timezone, not date() in UTC."""
    from zoneinfo import ZoneInfo

    return now.astimezone(ZoneInfo(tz_name)).date()
