"""Driver payouts, section 88.

A driver's balance is money they are owed for work already done. This is how
they ask for it and how the office answers. Both halves are audited inside the
same transaction as the money movement, because a payment trail that can be
missing is worse than none at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from domain.enums import ActorRole, SettlementDirection, SettlementStatus
from domain.wallet import (
    LedgerEntry,
    Settlement,
    WalletBalance,
    assert_can_collect,
    assert_can_request,
)
from shared import error_codes
from shared.clock import Clock
from shared.errors import NotFoundError
from shared.ids import IdGenerator
from shared.money import Money

# A payout costs the office a trip to the driver, or the driver a trip to the
# office. Below this the errand costs more than the money, so the default asks
# drivers to let it accumulate -- an operator can lower it from app_settings.
DEFAULT_MINIMUM_MINOR = 50_000        # 500 AFN


def read_balance(wallet) -> WalletBalance:
    c = wallet.currency
    return WalletBalance(
        available=Money(wallet.available_minor, c),
        pending=Money(wallet.pending_minor, c),
        lifetime_earned=Money(wallet.lifetime_earned_minor, c),
        lifetime_commission=Money(wallet.lifetime_commission_minor, c),
        lifetime_paid=Money(wallet.lifetime_paid_minor, c),
    )


def read_entry(row) -> LedgerEntry:
    return LedgerEntry(
        id=row.id,
        kind=row.kind,
        amount=Money(row.amount_minor, row.currency),
        balance_after=Money(row.balance_after_minor, row.currency),
        created_at=row.created_at,
        booking_id=row.booking_id,
        trip_id=row.trip_id,
        settlement_id=row.settlement_id,
        note=row.note,
    )


def read_settlement(row) -> Settlement:
    return Settlement(
        id=row.id,
        reference=row.reference,
        driver_id=row.driver_id,
        wallet_id=row.wallet_id,
        amount=Money(row.amount_minor, row.currency),
        period_start=row.period_start,
        period_end=row.period_end,
        direction=row.direction,
        status=row.status,
        paid_at=row.paid_at,
        processed_by=row.processed_by,
        rejection_reason=row.rejection_reason,
    )


@dataclass(frozen=True, slots=True)
class RequestSettlementCommand:
    driver_user_id: str
    amount_minor: int | None = None       # None means "all of it"
    request_id: str | None = None


class RequestSettlement:
    def __init__(
        self, *, drivers, wallets, settlements, numbers, settings, audit,
        clock: Clock, new_id: IdGenerator,
    ) -> None:
        self._drivers = drivers
        self._wallets = wallets
        self._settlements = settlements
        self._numbers = numbers
        self._settings = settings
        self._audit = audit
        self._clock = clock
        self._new_id = new_id

    def execute(self, cmd: RequestSettlementCommand) -> Settlement:
        driver = self._drivers.find_by_user(cmd.driver_user_id)
        if driver is None:
            raise NotFoundError(
                error_codes.DRIVER_NOT_FOUND, user_id=cmd.driver_user_id
            )

        # get_or_create takes a row lock, so the balance read below cannot move
        # under us between the check and the hold.
        wallet = self._wallets.get_or_create(driver.id, "AFN")
        balance = read_balance(wallet)

        open_row = self._settlements.find_open_for_driver(driver.id)
        amount = Money(
            cmd.amount_minor if cmd.amount_minor is not None
            else balance.amount_withdrawable.amount_minor,
            wallet.currency,
        )
        minimum = Money(
            self._settings.get_int("settlement.minimum_minor", DEFAULT_MINIMUM_MINOR),
            wallet.currency,
        )
        assert_can_request(
            balance,
            amount,
            minimum=minimum,
            open_settlement_reference=open_row.reference if open_row else None,
        )

        now = self._clock.now()
        # The period is what this payout covers. With no prior settlement it
        # runs from the driver's first day, so the first payout is not silently
        # dated to today and made to look like a single day's work.
        last_paid = self._settlements.for_driver(driver.id, limit=1)
        period_start: date = (
            last_paid[0].period_end if last_paid else driver.created_at.date()
        )
        row = self._settlements.create(
            id=self._new_id(),
            driver_id=driver.id,
            wallet_id=wallet.id,
            reference=self._numbers.allocate("settlement", year=now.year),
            period_start=period_start,
            period_end=now.date(),
            amount_minor=amount.amount_minor,
            currency=amount.currency,
            direction=SettlementDirection.PAYOUT.value,
            status=SettlementStatus.PENDING.value,
        )
        self._wallets.hold_for_settlement(
            wallet=wallet,
            amount_minor=amount.amount_minor,
            settlement_id=row.id,
            reference=row.reference,
        )
        self._audit.write(
            "settlement.requested",
            actor_id=cmd.driver_user_id,
            actor_role=ActorRole.DRIVER,
            entity_type="settlement",
            entity_id=row.id,
            after={
                "reference": row.reference,
                "amount_minor": amount.amount_minor,
                "currency": amount.currency,
            },
            request_id=cmd.request_id,
        )
        return read_settlement(row)


@dataclass(frozen=True, slots=True)
class RecordCollectionCommand:
    """The office records money a driver has handed in.

    Not a request: nobody is asking for anything, someone is writing down what
    already happened at the counter. The driver's debt drops when it is marked
    paid, not now, so a mistyped amount can still be rejected.
    """

    driver_id: str
    actor_id: str
    amount_minor: int | None = None       # None means "everything owed"
    request_id: str | None = None


class RecordCollection:
    def __init__(
        self, *, drivers, wallets, settlements, numbers, audit,
        clock: Clock, new_id: IdGenerator,
    ) -> None:
        self._drivers = drivers
        self._wallets = wallets
        self._settlements = settlements
        self._numbers = numbers
        self._audit = audit
        self._clock = clock
        self._new_id = new_id

    def execute(self, cmd: RecordCollectionCommand) -> Settlement:
        driver = self._drivers.find(cmd.driver_id)
        if driver is None:
            raise NotFoundError(error_codes.DRIVER_NOT_FOUND, driver_id=cmd.driver_id)

        wallet = self._wallets.get_or_create(driver.id, "AFN")
        balance = read_balance(wallet)
        open_row = self._settlements.find_open_for_driver(driver.id)
        amount = Money(
            cmd.amount_minor if cmd.amount_minor is not None
            else balance.amount_owed.amount_minor,
            wallet.currency,
        )
        assert_can_collect(
            balance,
            amount,
            open_settlement_reference=open_row.reference if open_row else None,
        )

        now = self._clock.now()
        last = self._settlements.for_driver(driver.id, limit=1)
        period_start: date = (
            last[0].period_end if last else driver.created_at.date()
        )
        row = self._settlements.create(
            id=self._new_id(),
            driver_id=driver.id,
            wallet_id=wallet.id,
            reference=self._numbers.allocate("settlement", year=now.year),
            period_start=period_start,
            period_end=now.date(),
            amount_minor=amount.amount_minor,
            currency=amount.currency,
            direction=SettlementDirection.COLLECTION.value,
            status=SettlementStatus.PENDING.value,
        )
        # The debt is held, not cleared: the money is only recognised when the
        # settlement is marked paid, so a wrong entry can still be rejected.
        self._wallets.hold_for_settlement(
            wallet=wallet,
            amount_minor=-amount.amount_minor,
            settlement_id=row.id,
            reference=row.reference,
        )
        self._audit.write(
            "settlement.collected",
            actor_id=cmd.actor_id,
            actor_role=ActorRole.ADMIN,
            entity_type="settlement",
            entity_id=row.id,
            after={
                "reference": row.reference,
                "amount_minor": amount.amount_minor,
                "currency": amount.currency,
                "direction": SettlementDirection.COLLECTION.value,
                "driver_id": driver.id,
            },
            request_id=cmd.request_id,
        )
        return read_settlement(row)


@dataclass(frozen=True, slots=True)
class DecideSettlementCommand:
    settlement_id: str
    to: SettlementStatus
    actor_id: str
    reason: str | None = None
    request_id: str | None = None


class DecideSettlement:
    """The office moves a payout along: accepted for processing, paid, refused.

    Every outcome is a declared transition, so a settlement can never be paid
    twice and a rejected one can never quietly become paid.
    """

    def __init__(self, *, wallets, settlements, audit, clock: Clock) -> None:
        self._wallets = wallets
        self._settlements = settlements
        self._audit = audit
        self._clock = clock

    def execute(self, cmd: DecideSettlementCommand) -> Settlement:
        row = self._settlements.find(cmd.settlement_id)
        if row is None:
            raise NotFoundError(
                error_codes.SETTLEMENT_NOT_FOUND, settlement_id=cmd.settlement_id
            )
        settlement = read_settlement(row)
        before = settlement.status
        now = self._clock.now()

        if cmd.to is SettlementStatus.REJECTED:
            settlement.reject(cmd.reason or "", at=now, by=cmd.actor_id)
        else:
            settlement.advance(cmd.to, at=now, by=cmd.actor_id)

        # Only now that the transition is legal does money move.
        wallet = self._wallets.find(row.wallet_id)
        if wallet is None:
            raise NotFoundError(error_codes.WALLET_NOT_FOUND, wallet_id=row.wallet_id)

        collection = settlement.direction is SettlementDirection.COLLECTION
        signed = -row.amount_minor if collection else row.amount_minor
        if settlement.status is SettlementStatus.PAID:
            self._wallets.settle_hold(wallet=wallet, amount_minor=signed)
        elif settlement.status is SettlementStatus.REJECTED:
            # Whatever was held goes back exactly as it was: a refused payout
            # returns a credit, a refused collection returns the debt.
            self._wallets.release_hold(
                wallet=wallet,
                amount_minor=signed,
                settlement_id=row.id,
                reference=row.reference,
            )

        row.status = settlement.status.value
        row.paid_at = settlement.paid_at
        row.processed_by = settlement.processed_by
        row.rejection_reason = settlement.rejection_reason
        row.version += 1
        self._settlements.save(row)

        self._audit.write(
            "settlement.decided",
            actor_id=cmd.actor_id,
            actor_role=ActorRole.ADMIN,
            entity_type="settlement",
            entity_id=row.id,
            before={"status": str(before)},
            after={
                "status": str(settlement.status),
                "reference": row.reference,
                "amount_minor": row.amount_minor,
                "reason": settlement.rejection_reason,
            },
            request_id=cmd.request_id,
        )
        return settlement
