"""Fixed-route pricing.

The first of two strategies. ``DynamicFare`` -- base + distance + vehicle +
demand -- will be the second, implementing the same ``FareStrategy`` interface,
so switching is configuration rather than a rewrite. Nothing that calls a
strategy knows which one it has.

A strategy computes and returns. It never persists, never reads a clock of its
own, and never decides whether the passenger is allowed to travel.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from application.ports.repositories import FareRepository
from domain.enums import RideKind
from domain.fare import FareBreakdownDraft, FareQuote
from shared import error_codes
from shared.errors import NotFoundError
from shared.money import Money


@dataclass(frozen=True, slots=True)
class FareRequest:
    route_id: str
    ride_kind: RideKind
    from_sequence: int
    to_sequence: int
    seat_count: int
    on: date
    vehicle_type_code: str | None = None
    currency: str = "AFN"


class FixedRouteFare:
    """A configured price per leg, multiplied by seats.

    For a private ride the vehicle is hired whole, so the configured price is
    the price regardless of how many people get in. For a shared ride the
    passenger buys seats, so it multiplies. Getting this the wrong way round
    would either give away private rides or overcharge families, so it is stated
    here once rather than inferred at each call site.
    """

    name = "fixed_route"

    def __init__(self, fares: FareRepository) -> None:
        self._fares = fares

    def quote(self, request: FareRequest) -> FareQuote:
        rule = self._fares.find_rule(
            route_id=request.route_id,
            ride_kind=request.ride_kind.value,
            from_sequence=request.from_sequence,
            to_sequence=request.to_sequence,
            vehicle_type_code=request.vehicle_type_code,
            on=request.on,
        )
        if rule is None:
            raise NotFoundError(
                error_codes.FARE_NOT_CONFIGURED,
                route_id=request.route_id,
                ride_kind=request.ride_kind.value,
                from_sequence=request.from_sequence,
                to_sequence=request.to_sequence,
            )

        unit = Money(rule.amount_minor, rule.amount_currency)
        draft = FareBreakdownDraft(currency=unit.currency)

        if request.ride_kind is RideKind.PRIVATE:
            draft.add("fare.component.private_vehicle", unit, quantity=1)
        else:
            draft.add("fare.component.seat", unit, quantity=request.seat_count)

        return FareQuote(
            components=tuple(draft.components),
            currency=unit.currency,
            ride_kind=request.ride_kind,
            seat_count=request.seat_count,
            route_id=request.route_id,
            from_sequence=request.from_sequence,
            to_sequence=request.to_sequence,
            fare_rule_id=rule.id,
        )
