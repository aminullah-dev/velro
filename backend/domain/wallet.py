"""The driver's money.

A wallet is not a balance -- it is a projection of an append-only ledger, and
the ledger is the record. Every rule here is written so that the two can be
reconciled: an entry always states the balance it produced, and money only ever
moves between the three named buckets, never into or out of nowhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from domain.enums import SettlementDirection, SettlementStatus, WalletEntryKind
from domain.lifecycles import SETTLEMENT_LIFECYCLE
from shared import error_codes
from shared.errors import ConflictError, ValidationError
from shared.money import Money


@dataclass(frozen=True, slots=True)
class WalletBalance:
    """What stands between the driver and VELRO, in either direction.

    ``available`` is signed, and the sign is the whole point. Fares are paid in
    cash at the vehicle (section 89), so the driver walks away holding the
    passenger's money and owing VELRO its share -- a negative balance. Only a
    fare the platform collected itself leaves VELRO owing the driver.

    ``pending`` is a settlement already in flight, in whichever direction, and
    must not be settled twice. ``lifetime_earned`` is what the driver made
    regardless of who held the notes.
    """

    available: Money
    pending: Money
    lifetime_earned: Money
    lifetime_commission: Money
    lifetime_paid: Money

    @property
    def owes_platform(self) -> bool:
        return self.available.amount_minor < 0

    @property
    def amount_owed(self) -> Money:
        """What the driver owes VELRO, as a positive figure. Zero if none."""
        return Money(max(0, -self.available.amount_minor), self.available.currency)

    @property
    def amount_withdrawable(self) -> Money:
        """What VELRO owes the driver, as a positive figure. Zero if none."""
        return Money(max(0, self.available.amount_minor), self.available.currency)

    @property
    def direction(self) -> SettlementDirection:
        """Which way the next settlement would move money."""
        return (
            SettlementDirection.COLLECTION
            if self.owes_platform
            else SettlementDirection.PAYOUT
        )

    @property
    def total_held(self) -> Money:
        """Everything outstanding, whatever bucket it sits in."""
        return self.available + self.pending


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    id: str
    kind: WalletEntryKind
    amount: Money                     # signed: a payout is negative
    balance_after: Money
    created_at: datetime
    booking_id: str | None = None
    trip_id: str | None = None
    settlement_id: str | None = None
    note: str | None = None

    @property
    def is_credit(self) -> bool:
        return self.amount.amount_minor > 0


@dataclass(slots=True)
class Settlement:
    """A payout: the driver asks, the office pays.

    Cash fares mean the driver already holds the passenger's money and owes
    VELRO its commission -- so in practice a settlement is as often the driver
    paying in as being paid out. The direction is the operator's concern; what
    this enforces is that an amount is agreed once, cannot be requested twice
    over the same money, and lands in exactly one terminal state.
    """

    id: str
    reference: str                    # STL-2026-000001
    driver_id: str
    wallet_id: str
    amount: Money
    period_start: date
    period_end: date
    direction: SettlementDirection = SettlementDirection.PAYOUT
    status: SettlementStatus = SettlementStatus.PENDING
    paid_at: datetime | None = None
    processed_by: str | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        # Raw rows arrive as strings; comparing a str to a StrEnum member by
        # identity silently answers False everywhere it matters.
        if not isinstance(self.status, SettlementStatus):
            self.status = SettlementStatus(self.status)
        if not isinstance(self.direction, SettlementDirection):
            self.direction = SettlementDirection(self.direction)
        if self.amount.amount_minor <= 0:
            raise ValidationError(
                error_codes.SETTLEMENT_AMOUNT_INVALID,
                settlement_id=self.id,
                amount_minor=self.amount.amount_minor,
            )
        if self.period_end < self.period_start:
            raise ValidationError(
                error_codes.SETTLEMENT_AMOUNT_INVALID,
                settlement_id=self.id,
                reason="period_reversed",
            )

    @property
    def is_open(self) -> bool:
        """Still consuming the driver's pending balance."""
        return self.status in (SettlementStatus.PENDING, SettlementStatus.PROCESSING)

    def advance(self, to: SettlementStatus, *, at: datetime, by: str | None = None) -> None:
        SETTLEMENT_LIFECYCLE.check(self.status, to, settlement_id=self.id)
        self.status = to
        self.processed_by = by
        if to is SettlementStatus.PAID:
            self.paid_at = at

    def reject(self, reason: str, *, at: datetime, by: str | None = None) -> None:
        if not reason.strip():
            raise ValidationError(
                error_codes.SETTLEMENT_AMOUNT_INVALID,
                settlement_id=self.id,
                reason="rejection_reason_empty",
            )
        self.advance(SettlementStatus.REJECTED, at=at, by=by)
        # Set after advance: an illegal transition must leave the record
        # untouched rather than annotated with a reason that never applied.
        self.rejection_reason = reason.strip()


def assert_can_request(
    balance: WalletBalance,
    amount: Money,
    *,
    minimum: Money,
    open_settlement_reference: str | None = None,
) -> None:
    """The ways a payout request is refused.

    Kept as one function so the driver app, the admin panel and the API refuse
    for the same reasons in the same order -- the driver should never be told
    "too small" by one surface and "already requested" by another.
    """
    if open_settlement_reference is not None:
        raise ConflictError(
            error_codes.SETTLEMENT_ALREADY_REQUESTED,
            reference=open_settlement_reference,
        )
    # Direction first. A driver holding cash owes VELRO rather than being owed,
    # and asking to be paid out of a debt is the wrong direction, not a bad
    # amount -- reporting it as an amount problem sends them looking for money
    # that was never theirs to withdraw.
    if balance.owes_platform:
        raise ConflictError(
            error_codes.SETTLEMENT_DIRECTION_INVALID,
            owed_minor=balance.amount_owed.amount_minor,
            currency=balance.amount_owed.currency,
        )
    if amount.amount_minor <= 0:
        raise ValidationError(
            error_codes.SETTLEMENT_AMOUNT_INVALID, amount_minor=amount.amount_minor
        )
    if amount.amount_minor > balance.available.amount_minor:
        raise ConflictError(
            error_codes.WALLET_INSUFFICIENT_BALANCE,
            requested_minor=amount.amount_minor,
            available_minor=balance.available.amount_minor,
        )
    if amount.amount_minor < minimum.amount_minor:
        raise ValidationError(
            error_codes.SETTLEMENT_BELOW_MINIMUM,
            requested_minor=amount.amount_minor,
            minimum_minor=minimum.amount_minor,
            currency=minimum.currency,
        )


def assert_can_collect(
    balance: WalletBalance,
    amount: Money,
    *,
    open_settlement_reference: str | None = None,
) -> None:
    """Recording what a driver has paid in.

    No minimum: the minimum exists so a payout is worth the journey, and the
    driver is already standing at the office when this is recorded. Paying more
    than is owed is refused rather than left to create a credit nobody intended.
    """
    if open_settlement_reference is not None:
        raise ConflictError(
            error_codes.SETTLEMENT_ALREADY_REQUESTED,
            reference=open_settlement_reference,
        )
    if amount.amount_minor <= 0:
        raise ValidationError(
            error_codes.SETTLEMENT_AMOUNT_INVALID, amount_minor=amount.amount_minor
        )
    if amount.amount_minor > balance.amount_owed.amount_minor:
        raise ConflictError(
            error_codes.SETTLEMENT_AMOUNT_INVALID,
            requested_minor=amount.amount_minor,
            owed_minor=balance.amount_owed.amount_minor,
        )
