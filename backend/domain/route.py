"""Routes.

Section 12 of the product specification is explicit: routes must not be
hand-created per village. A route *template* therefore carries an origin scope
rather than a single origin, and a generator materialises concrete routes for
every station in that scope. Adding a village to Siahgird automatically yields
its Charikar, Qarabagh and Kabul routes.

A route is not a trip. A route is the standing definition of a path; a trip is
one vehicle travelling it on one day at one time.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.enums import OriginScope, RouteStatus, RouteType
from shared import error_codes
from shared.errors import ConflictError, ValidationError


@dataclass(slots=True)
class RouteStop:
    """One ordered point on a route. Exactly one of station_id / destination_id is set."""

    id: str
    route_id: str
    sequence: int
    station_id: str | None = None
    destination_id: str | None = None
    is_pickup: bool = True
    is_dropoff: bool = True

    def __post_init__(self) -> None:
        if (self.station_id is None) == (self.destination_id is None):
            raise ValidationError(
                error_codes.VALIDATION_FAILED,
                field="route_stop",
                reason="exactly one of station_id or destination_id must be set",
            )
        if self.sequence < 0:
            raise ValidationError(error_codes.VALIDATION_FAILED, field="sequence")

    @property
    def place_id(self) -> str:
        return self.station_id or self.destination_id  # type: ignore[return-value]


@dataclass(slots=True)
class Route:
    id: str
    code: str
    route_type: RouteType
    origin_station_id: str
    destination_id: str
    stops: list[RouteStop] = field(default_factory=list)
    distance_m: int | None = None
    duration_minutes: int | None = None
    template_id: str | None = None
    status: RouteStatus = RouteStatus.DRAFT

    # -- invariants -------------------------------------------------------

    def __post_init__(self) -> None:
        if self.distance_m is not None and self.distance_m < 0:
            raise ValidationError(error_codes.VALIDATION_FAILED, field="distance_m")
        if self.duration_minutes is not None and self.duration_minutes < 0:
            raise ValidationError(error_codes.VALIDATION_FAILED, field="duration_minutes")

    def ordered_stops(self) -> list[RouteStop]:
        stops = sorted(self.stops, key=lambda s: s.sequence)
        sequences = [s.sequence for s in stops]
        if len(set(sequences)) != len(sequences):
            raise ValidationError(
                error_codes.ROUTE_STOPS_OUT_OF_ORDER, route_id=self.id, sequences=sequences
            )
        return stops

    @property
    def is_active(self) -> bool:
        return self.status is RouteStatus.ACTIVE

    def assert_active(self) -> None:
        if not self.is_active:
            raise ConflictError(
                error_codes.ROUTE_DISABLED, route_id=self.id, status=str(self.status)
            )

    # -- segment travel ---------------------------------------------------

    def index_of(self, place_id: str) -> int | None:
        for stop in self.ordered_stops():
            if stop.place_id == place_id:
                return stop.sequence
        return None

    def serves(self, origin_place_id: str, destination_place_id: str) -> bool:
        """True when both points sit on this route, in travelling order.

        This is what lets a passenger board at an intermediate station: a route
        Khishki -> Siahgird -> Charikar serves Siahgird -> Charikar too.
        """
        origin = self.index_of(origin_place_id)
        destination = self.index_of(destination_place_id)
        if origin is None or destination is None:
            return False
        if origin >= destination:
            return False
        stops = {s.sequence: s for s in self.ordered_stops()}
        return stops[origin].is_pickup and stops[destination].is_dropoff

    def segment(self, origin_place_id: str, destination_place_id: str) -> tuple[int, int]:
        """The (from_sequence, to_sequence) pair used to price and book a leg."""
        if not self.serves(origin_place_id, destination_place_id):
            raise ConflictError(
                error_codes.ROUTE_NOT_RESOLVABLE,
                route_id=self.id,
                origin=origin_place_id,
                destination=destination_place_id,
            )
        origin = self.index_of(origin_place_id)
        destination = self.index_of(destination_place_id)
        return origin, destination  # type: ignore[return-value]


@dataclass(slots=True)
class RouteTemplate:
    """The rule that generates routes, so no village is ever wired up by hand."""

    id: str
    code: str
    name: str
    origin_scope: OriginScope
    origin_ref_id: str          # district / village / station id, per the scope
    destination_id: str
    route_type: RouteType
    vehicle_type_code: str
    default_seat_capacity: int
    intermediate_destination_ids: list[str] = field(default_factory=list)
    distance_m: int | None = None
    duration_minutes: int | None = None
    status: RouteStatus = RouteStatus.ACTIVE

    def __post_init__(self) -> None:
        if self.default_seat_capacity <= 0:
            raise ValidationError(
                error_codes.VEHICLE_CAPACITY_INVALID, capacity=self.default_seat_capacity
            )
