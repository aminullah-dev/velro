"""Fares.

Two rules make this correct rather than merely working:

1. A price is never computed on a client. The mobile apps display what the
   backend quoted and nothing else (section 29).
2. The quote is persisted onto the booking. Editing a route's price tomorrow
   must not change what a passenger was charged yesterday -- the same rule the
   platform applies to exchange rates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from domain.enums import RideKind
from shared import error_codes
from shared.errors import ValidationError
from shared.money import Money


@dataclass(frozen=True, slots=True)
class FareComponent:
    """One line of the breakdown. The key is an i18n key, never a sentence."""

    key: str            # fare.component.base, fare.component.per_seat, ...
    amount: Money
    quantity: int = 1

    def total(self) -> Money:
        return self.amount * self.quantity


@dataclass(frozen=True, slots=True)
class FareQuote:
    """What a passenger is told they will pay, and what the booking stores."""

    components: tuple[FareComponent, ...]
    currency: str
    ride_kind: RideKind
    seat_count: int
    route_id: str
    from_sequence: int
    to_sequence: int
    fare_rule_id: str | None = None

    def __post_init__(self) -> None:
        if self.seat_count <= 0:
            raise ValidationError(
                error_codes.BOOKING_SEAT_COUNT_INVALID, seat_count=self.seat_count
            )
        if any(c.amount.currency != self.currency for c in self.components):
            raise ValidationError(error_codes.VALIDATION_FAILED, field="currency")
        if self.total().is_negative:
            raise ValidationError(
                error_codes.FARE_NEGATIVE, amount_minor=self.total().amount_minor
            )

    def total(self) -> Money:
        running = Money.zero(self.currency)
        for component in self.components:
            running = running + component.total()
        return running

    def per_seat(self) -> Money:
        total = self.total()
        return Money(total.amount_minor // self.seat_count, total.currency)


@dataclass(slots=True)
class FareRule:
    """A configured price for a leg of a route. Versioned, never edited in place.

    Superseding a price closes the old row with ``valid_to`` and inserts a new
    one, so the price history is auditable and a historical booking can always
    be explained.
    """

    id: str
    route_id: str
    ride_kind: RideKind
    vehicle_type_code: str | None
    from_sequence: int
    to_sequence: int
    amount: Money
    valid_from: date
    valid_to: date | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        if self.amount.is_negative:
            raise ValidationError(
                error_codes.FARE_NEGATIVE, amount_minor=self.amount.amount_minor
            )
        if self.from_sequence >= self.to_sequence:
            raise ValidationError(
                error_codes.ROUTE_STOPS_OUT_OF_ORDER,
                from_sequence=self.from_sequence,
                to_sequence=self.to_sequence,
            )
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise ValidationError(error_codes.VALIDATION_FAILED, field="valid_to")

    def covers(self, on: date) -> bool:
        return self.valid_from <= on and (self.valid_to is None or on <= self.valid_to)

    def applies_to(
        self, ride_kind: RideKind, from_sequence: int, to_sequence: int, vehicle_type: str | None
    ) -> bool:
        if self.ride_kind is not ride_kind:
            return False
        if self.vehicle_type_code is not None and self.vehicle_type_code != vehicle_type:
            return False
        return self.from_sequence == from_sequence and self.to_sequence == to_sequence


@dataclass(frozen=True, slots=True)
class CommissionSplit:
    """How one fare divides between the driver and VELRO."""

    gross: Money
    platform: Money
    driver: Money
    rate_basis_points: int

    @classmethod
    def of(cls, gross: Money, rate_basis_points: int) -> CommissionSplit:
        if not 0 <= rate_basis_points <= 10_000:
            raise ValidationError(
                error_codes.COMMISSION_RATE_INVALID, rate_basis_points=rate_basis_points
            )
        platform, driver = gross.split_off(rate_basis_points)
        return cls(gross, platform, driver, rate_basis_points)

    def __post_init__(self) -> None:
        if self.platform + self.driver != self.gross:
            raise ValidationError(error_codes.COMMISSION_RATE_INVALID, reason="split_mismatch")


@dataclass(slots=True)
class FareBreakdownDraft:
    """Builder used by fare strategies. Domain-side, so no strategy invents its own shape."""

    currency: str
    components: list[FareComponent] = field(default_factory=list)

    def add(self, key: str, amount: Money, quantity: int = 1) -> FareBreakdownDraft:
        if amount.currency != self.currency:
            raise ValidationError(error_codes.VALIDATION_FAILED, field="currency")
        self.components.append(FareComponent(key=key, amount=amount, quantity=quantity))
        return self
