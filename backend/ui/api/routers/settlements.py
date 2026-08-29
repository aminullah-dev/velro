"""Driver payouts, section 88.

Split from the driver router because both halves of a payout live here: the
driver asking and the office answering. Reading them side by side is the only
way to be sure the money that leaves one bucket arrives in the other.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from application.use_cases.settlements import (
    DecideSettlement,
    DecideSettlementCommand,
    RequestSettlement,
    RequestSettlementCommand,
    read_balance,
    read_entry,
)
from domain.enums import SettlementStatus
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


class SettlementOut(Schema):
    id: str
    reference: str
    amount: MoneyOut
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


def _settlement_out(s, *, driver_name=None, driver_phone=None) -> SettlementOut:
    return SettlementOut(
        id=s.id,
        reference=s.reference,
        amount=MoneyOut.of(s.amount),
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
            # The app needs all three to say why the button is disabled: too
            # little, or one already in flight. Deriving it client-side would
            # put the rule in two places and let them disagree.
            "minimum": MoneyOut.of(Money(minimum, wallet.currency)).model_dump(),
            "can_request": open_one is None
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
