"""Driver payouts, section 88.

Split from the driver router because both halves of a payout live here: the
driver asking and the office answering. Reading them side by side is the only
way to be sure the money that leaves one bucket arrives in the other.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from application.use_cases.settlements import (
    DecideSettlement,
    DecideSettlementCommand,
    RecordCollection,
    RecordCollectionCommand,
    RequestSettlement,
    RequestSettlementCommand,
    read_balance,
    read_entry,
)
from domain.enums import SettlementStatus, WalletEntryKind
from shared import error_codes
from shared.errors import NotFoundError, ValidationError
from shared.money import Money
from ui.api import deps
from ui.api.errors import ok
from ui.api.schemas.common import MoneyOut, Schema


class LedgerEntryOut(Schema):
    id: str
    kind: str
    amount: MoneyOut
    balance_after: MoneyOut
    created_at: str
    booking_id: str | None
    trip_id: str | None
    settlement_id: str | None
    note: str | None


class EarningsBucketOut(Schema):
    """One day, week or month of a driver's money."""

    #: ISO date of the bucket's first day. The client formats it -- the server
    #: has no idea whether this driver reads Gregorian or Shamsi.
    starts_on: str
    earned: MoneyOut
    commission: MoneyOut
    #: What the driver actually keeps: earned minus commission. Sent rather
    #: than left to the client, so the app and the office can never disagree
    #: about a number the driver will compare against cash in his pocket.
    net: MoneyOut
    trips: int


class EarningsSummaryOut(Schema):
    period: str
    #: Oldest first, and gaps are filled with zero buckets. A chart that simply
    #: omits a day the driver did not work draws his quiet Friday as if it were
    #: the same width as a busy Monday.
    buckets: list[EarningsBucketOut]


class SettlementOut(Schema):
    id: str
    reference: str
    amount: MoneyOut
    direction: str
    status: str
    period_start: str
    period_end: str
    paid_at: str | None
    rejection_reason: str | None
    driver_id: str
    driver_name: str | None = None
    driver_phone: str | None = None


class RequestSettlementIn(Schema):
    # Absent means "everything available". A driver asking for all of it should
    # not have to restate a number the server already knows, and cannot get it
    # wrong by a few afghani if a fare lands while they are typing.
    amount_minor: int | None = Field(default=None, ge=1)


class DecideSettlementIn(Schema):
    to: str
    reason: str | None = Field(default=None, max_length=500)


class RecordCollectionIn(Schema):
    driver_id: str
    amount_minor: int | None = Field(default=None, ge=1)


def _settlement_out(s, *, driver_name=None, driver_phone=None) -> SettlementOut:
    return SettlementOut(
        id=s.id,
        reference=s.reference,
        amount=MoneyOut.of(s.amount),
        direction=str(s.direction),
        status=str(s.status),
        period_start=s.period_start.isoformat(),
        period_end=s.period_end.isoformat(),
        paid_at=s.paid_at.isoformat() if s.paid_at else None,
        rejection_reason=s.rejection_reason,
        driver_id=s.driver_id,
        driver_name=driver_name,
        driver_phone=driver_phone,
    )


driver_router = APIRouter(prefix="/driver", tags=["driver"])


@driver_router.get("/earnings/ledger")
def ledger(
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    wallets: Annotated[object, Depends(deps.wallets)],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Why the balance is what it is.

    A number with no explanation behind it is the fastest way to lose a
    driver's trust, so every fare and every deduction is listed with the
    balance it produced.
    """
    driver = _driver_of(drivers, actor.user_id)
    wallet = wallets.get_or_create(driver.id, "AFN")
    rows = wallets.ledger(wallet.id, limit=limit + 1, offset=offset)
    page, has_more = rows[:limit], len(rows) > limit
    return ok(
        {
            "entries": [
                LedgerEntryOut(
                    id=e.id,
                    kind=str(e.kind),
                    amount=MoneyOut.of(e.amount),
                    balance_after=MoneyOut.of(e.balance_after),
                    created_at=e.created_at.isoformat(),
                    booking_id=e.booking_id,
                    trip_id=e.trip_id,
                    settlement_id=e.settlement_id,
                    note=e.note,
                ).model_dump()
                for e in (read_entry(r) for r in page)
            ],
            "has_more": has_more,
            "next_offset": offset + len(page),
        }
    )


@driver_router.get("/earnings/summary")
def earnings_summary(
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    wallets: Annotated[object, Depends(deps.wallets)],
    period: Annotated[str, Query(pattern="^(DAY|WEEK|MONTH)$")] = "DAY",
    buckets: Annotated[int, Query(ge=1, le=53)] = 7,
) -> dict:
    """Earnings grouped into days, weeks or months.

    The ledger answers "why is my balance this?"; this answers "how did last
    week go?". Lifetime totals cannot: a driver comparing this week against
    last has nothing to compare, and a number that only ever grows tells him
    nothing about whether today was worth the fuel.

    Buckets are bounded at 53 -- a year of weeks -- so a request cannot walk
    the whole table.
    """
    driver = _driver_of(drivers, actor.user_id)
    wallet = wallets.get_or_create(driver.id, "AFN")

    starts = _bucket_starts(period, buckets)
    rows = wallets.entries_since(wallet.id, since=starts[0])

    earned = {s: 0 for s in starts}
    commission = {s: 0 for s in starts}
    trips = {s: 0 for s in starts}
    for row in rows:
        entry = read_entry(row)
        start = _bucket_for(entry.created_at, period, starts)
        if start is None:
            continue
        minor = entry.amount.amount_minor
        if entry.kind == WalletEntryKind.TRIP_EARNING:
            earned[start] += minor
            trips[start] += 1
        elif entry.kind == WalletEntryKind.COMMISSION:
            # Stored negative. Commission is reported as the positive amount
            # deducted, because "commission: -125" reads to a driver as money
            # he was given.
            commission[start] += abs(minor)

    currency = wallet.currency
    return ok(
        EarningsSummaryOut(
            period=period,
            buckets=[
                EarningsBucketOut(
                    starts_on=s.date().isoformat(),
                    earned=MoneyOut.of(Money(earned[s], currency)),
                    commission=MoneyOut.of(Money(commission[s], currency)),
                    net=MoneyOut.of(Money(earned[s] - commission[s], currency)),
                    trips=trips[s],
                )
                for s in starts
            ],
        ).model_dump()
    )


def _bucket_starts(period: str, count: int) -> list[datetime]:
    """The first instant of each bucket, oldest first, ending with the one now.

    Weeks start on Saturday: the Afghan week runs Saturday to Friday, and a
    Monday-based week would cut every driver's weekend in half and report it
    as two quiet weeks.
    """
    now = datetime.now(UTC)
    today = datetime(now.year, now.month, now.day, tzinfo=UTC)
    if period == "DAY":
        return [today - timedelta(days=i) for i in range(count - 1, -1, -1)]
    if period == "WEEK":
        # Saturday = 5 in Python's Monday-is-0 numbering.
        this_week = today - timedelta(days=(today.weekday() - 5) % 7)
        return [this_week - timedelta(weeks=i) for i in range(count - 1, -1, -1)]
    starts = []
    year, month = today.year, today.month
    for _ in range(count):
        starts.append(datetime(year, month, 1, tzinfo=UTC))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(starts))


def _bucket_for(when: datetime, period: str, starts: list[datetime]) -> datetime | None:
    """The bucket an entry belongs to, or None if it predates the window.

    Walks backwards so the newest bucket -- the one most entries land in --
    is found first.
    """
    for start in reversed(starts):
        if when >= start:
            return start
    return None


@driver_router.get("/settlements")
def my_settlements(
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    wallets: Annotated[object, Depends(deps.wallets)],
    settlements: Annotated[object, Depends(deps.settlements)],
    app_settings: Annotated[object, Depends(deps.app_settings)],
) -> dict:
    from application.use_cases.settlements import (
        DEFAULT_MINIMUM_MINOR,
        read_settlement,
    )

    driver = _driver_of(drivers, actor.user_id)
    wallet = wallets.get_or_create(driver.id, "AFN")
    balance = read_balance(wallet)
    rows = settlements.for_driver(driver.id, limit=20)
    history = [read_settlement(r) for r in rows]
    minimum = app_settings.get_int("settlement.minimum_minor", DEFAULT_MINIMUM_MINOR)
    open_one = next((s for s in history if s.is_open), None)
    return ok(
        {
            "settlements": [_settlement_out(s).model_dump() for s in history],
            # The app needs all of these to say why the button is absent: the
            # driver owes rather than is owed, the amount is too small, or one
            # is already in flight. Deciding it client-side would put the rule
            # in two places and let them disagree.
            "minimum": MoneyOut.of(Money(minimum, wallet.currency)).model_dump(),
            "direction": str(balance.direction),
            "amount_owed": MoneyOut.of(balance.amount_owed).model_dump(),
            "amount_withdrawable": MoneyOut.of(balance.amount_withdrawable).model_dump(),
            "can_request": open_one is None
            and not balance.owes_platform
            and balance.available.amount_minor >= minimum,
            "open_reference": open_one.reference if open_one else None,
        }
    )


@driver_router.post("/settlements", status_code=201)
def request_settlement(
    body: RequestSettlementIn,
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    wallets: Annotated[object, Depends(deps.wallets)],
    settlements: Annotated[object, Depends(deps.settlements)],
    numbers: Annotated[object, Depends(deps.numbers)],
    app_settings: Annotated[object, Depends(deps.app_settings)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    use_case = RequestSettlement(
        drivers=drivers, wallets=wallets, settlements=settlements, numbers=numbers,
        settings=app_settings, audit=audit, clock=deps.clock(), new_id=deps.new_id,
    )
    result = use_case.execute(
        RequestSettlementCommand(
            driver_user_id=actor.user_id, amount_minor=body.amount_minor
        )
    )
    return ok(_settlement_out(result).model_dump())


admin_router = APIRouter(prefix="/admin/settlements", tags=["admin"])


@admin_router.get("")
def queue(
    actor: Annotated[deps.Actor, Depends(deps.require_finance)],
    settlements: Annotated[object, Depends(deps.settlements)],
    drivers: Annotated[object, Depends(deps.drivers)],
    users: Annotated[object, Depends(deps.users)],
) -> dict:
    from application.use_cases.settlements import read_settlement

    rows = settlements.open_queue(limit=100)
    out = []
    for row in rows:
        driver = drivers.find(row.driver_id)
        user = users.find(driver.user_id) if driver else None
        out.append(
            _settlement_out(
                read_settlement(row),
                driver_name=user.full_name if user else None,
                driver_phone=user.phone if user else None,
            ).model_dump()
        )
    return ok(out)


class DebtorOut(Schema):
    driver_id: str
    driver_name: str | None
    driver_phone: str | None
    amount_owed: MoneyOut
    completed_trips: int


@admin_router.get("/debtors")
def debtors(
    actor: Annotated[deps.Actor, Depends(deps.require_finance)],
    wallets: Annotated[object, Depends(deps.wallets)],
    drivers: Annotated[object, Depends(deps.drivers)],
    users: Annotated[object, Depends(deps.users)],
) -> dict:
    """Who is holding VELRO's money.

    With cash fares this is the ordinary state of an active driver, so it is a
    working list rather than an exception report.
    """
    rows = wallets.debtors(limit=100)
    driver_rows = {d.id: d for d in drivers.by_ids({w.driver_id for w in rows})}
    user_rows = {
        u.id: u for u in users.by_ids({d.user_id for d in driver_rows.values()})
    }
    out = []
    for wallet in rows:
        driver = driver_rows.get(wallet.driver_id)
        user = user_rows.get(driver.user_id) if driver else None
        out.append(
            DebtorOut(
                driver_id=wallet.driver_id,
                driver_name=user.full_name if user else None,
                driver_phone=user.phone if user else None,
                amount_owed=MoneyOut.of(
                    Money(-wallet.available_minor, wallet.currency)
                ),
                completed_trips=driver.completed_trips if driver else 0,
            ).model_dump()
        )
    return ok(out)


@admin_router.post("/collect", status_code=201)
def record_collection(
    body: RecordCollectionIn,
    actor: Annotated[deps.Actor, Depends(deps.require_finance)],
    drivers: Annotated[object, Depends(deps.drivers)],
    wallets: Annotated[object, Depends(deps.wallets)],
    settlements: Annotated[object, Depends(deps.settlements)],
    numbers: Annotated[object, Depends(deps.numbers)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    """Record cash a driver has handed in against what they owe.

    Section 89: fares are collected at the vehicle, so the usual direction is
    the driver paying the platform, not the other way round.
    """
    use_case = RecordCollection(
        drivers=drivers, wallets=wallets, settlements=settlements, numbers=numbers,
        audit=audit, clock=deps.clock(), new_id=deps.new_id,
    )
    result = use_case.execute(
        RecordCollectionCommand(
            driver_id=body.driver_id,
            actor_id=actor.user_id,
            amount_minor=body.amount_minor,
        )
    )
    return ok(_settlement_out(result).model_dump())


@admin_router.post("/{settlement_id}/decide")
def decide(
    settlement_id: str,
    body: DecideSettlementIn,
    actor: Annotated[deps.Actor, Depends(deps.require_finance)],
    wallets: Annotated[object, Depends(deps.wallets)],
    settlements: Annotated[object, Depends(deps.settlements)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    try:
        target = SettlementStatus(body.to)
    except ValueError:
        raise ValidationError(
            error_codes.SETTLEMENT_INVALID_TRANSITION,
            requested=body.to,
            allowed=[s.value for s in SettlementStatus],
        ) from None

    use_case = DecideSettlement(
        wallets=wallets, settlements=settlements, audit=audit, clock=deps.clock()
    )
    result = use_case.execute(
        DecideSettlementCommand(
            settlement_id=settlement_id,
            to=target,
            actor_id=actor.user_id,
            reason=body.reason,
        )
    )
    return ok(_settlement_out(result).model_dump())


def _driver_of(drivers, user_id: str):
    row = drivers.find_by_user(user_id)
    if row is None:
        raise NotFoundError(error_codes.DRIVER_NOT_FOUND, user_id=user_id)
    return row
