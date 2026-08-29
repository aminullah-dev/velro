"""Getting help.

Two very different things behind one word.

The first is the emergency numbers, and the design decision that matters is
that this endpoint needs no token. Everything else in VELRO is behind
`require_*`; this is not, because a passenger whose session expired in a valley
with no data must still be able to see 119. A signed-out phone that cannot show
an emergency number is the failure this exists to prevent, and the numbers are
public information — printed on posters — so there is nothing to protect.

The second is a support ticket: asynchronous, needs data, and read by a person
during office hours. The screen must never let those two be confused. VELRO
cannot send anyone to you, and the words on the report button say so.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from application.use_cases.support import (
    DecideTicket,
    DecideTicketCommand,
    RaiseTicket,
    RaiseTicketCommand,
    ReplyCommand,
    ReplyToTicket,
    to_ticket,
)
from domain.enums import ActorRole, TicketStatus
from domain.support import CATEGORIES, URGENT_CATEGORIES
from shared import error_codes
from shared.errors import NotFoundError
from ui.api import deps
from ui.api.errors import ok
from ui.api.schemas.common import Schema

router = APIRouter(tags=["support"])

STAFF_ROLES = frozenset({ActorRole.DISPATCHER, ActorRole.ADMIN, ActorRole.SYSTEM})


class ContactsOut(Schema):
    """What to dial, and what VELRO is honest about not being."""

    emergency_numbers: list[str]
    velro_number: str | None
    categories: list[str]
    urgent_categories: list[str]


class RaiseTicketIn(Schema):
    category_code: str = Field(min_length=1, max_length=40)
    subject: str = Field(default="", max_length=200)
    body: str = Field(min_length=1, max_length=4000)
    trip_id: str | None = None
    booking_id: str | None = None


class MessageOut(Schema):
    id: str
    author_role: str
    body: str
    is_internal: bool
    sent_at: datetime


class TicketOut(Schema):
    id: str
    reference: str
    category_code: str
    subject: str
    status: str
    is_urgent: bool
    trip_id: str | None
    booking_id: str | None
    created_at: datetime
    resolved_at: datetime | None
    messages: list[MessageOut]


class ReplyIn(Schema):
    body: str = Field(min_length=1, max_length=4000)
    # Only staff may set this, and the use case enforces that rather than
    # trusting the flag.
    is_internal: bool = False


class DecideTicketIn(Schema):
    status: str = Field(pattern=r"^(IN_PROGRESS|RESOLVED|CLOSED)$")


def _ticket_out(row, message_rows, *, to_staff: bool) -> TicketOut:
    ticket = to_ticket(row, message_rows)
    return TicketOut(
        id=row.id,
        reference=row.reference,
        category_code=row.category_code,
        subject=row.subject,
        status=row.status,
        is_urgent=ticket.is_urgent,
        trip_id=row.trip_id,
        booking_id=row.booking_id,
        created_at=row.created_at,
        resolved_at=row.resolved_at,
        messages=[
            MessageOut(
                id=m.id,
                author_role=m.author_role.value,
                body=m.body,
                is_internal=m.is_internal,
                sent_at=m.sent_at or row.created_at,
            )
            for m in ticket.visible_messages(to_staff=to_staff)
        ],
    )


# -- what to dial -------------------------------------------------------

@router.get("/support/contacts")
def contacts(
    settings: Annotated[object, Depends(deps.app_settings)],
) -> dict:
    """Deliberately unauthenticated. See the module docstring.

    The client caches this and ships a compiled-in copy, so the numbers are
    available on a handset that has never reached the server. This endpoint
    exists so an operator can change them without a release, not so the phone
    can find them in an emergency -- by then it is too late to ask.
    """
    velro = settings.get_str("support.contact_phone", "").strip()
    return ok(
        ContactsOut(
            emergency_numbers=[
                n for n in settings.get_list("support.emergency_numbers", []) if n
            ],
            # A placeholder number is worse than no button: it dials nothing at
            # the moment somebody is frightened. The default in settings.py is
            # +93700000000, so this check is not hypothetical.
            velro_number=velro if _is_dialable(velro) else None,
            categories=sorted(CATEGORIES),
            urgent_categories=sorted(URGENT_CATEGORIES),
        ).model_dump()
    )


def _is_dialable(number: str) -> bool:
    digits = [c for c in number if c.isdigit()]
    if len(digits) < 6:
        return False
    # All-zeros after the country code is the shape of a placeholder.
    return any(d != "0" for d in digits[3:])


# -- the passenger's and driver's side ----------------------------------

@router.post("/support/tickets", status_code=201)
def raise_ticket(
    body: RaiseTicketIn,
    actor: deps.ActorDep,
    tickets: Annotated[object, Depends(deps.support_tickets)],
    messages: Annotated[object, Depends(deps.ticket_messages)],
    numbers: Annotated[object, Depends(deps.numbers)],
    notifier: Annotated[object, Depends(deps.notifier)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    use_case = RaiseTicket(
        tickets=tickets, messages=messages, numbers=numbers, audit=audit,
        notifier=notifier, clock=deps.clock(), new_id=deps.new_id,
    )
    result = use_case.execute(
        RaiseTicketCommand(
            user_id=actor.user_id,
            actor_role=actor.role,
            category_code=body.category_code.strip().upper(),
            subject=body.subject,
            body=body.body,
            trip_id=body.trip_id,
            booking_id=body.booking_id,
        )
    )
    payload = asdict(result)
    payload["status"] = result.status.value
    return ok(payload)


@router.get("/support/tickets")
def my_tickets(
    actor: deps.ActorDep,
    tickets: Annotated[object, Depends(deps.support_tickets)],
    messages: Annotated[object, Depends(deps.ticket_messages)],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> dict:
    rows = tickets.for_user(actor.user_id, limit=limit)
    return ok(
        [
            _ticket_out(row, messages.for_ticket(row.id), to_staff=False).model_dump()
            for row in rows
        ]
    )


@router.get("/support/tickets/{ticket_id}")
def my_ticket(
    ticket_id: str,
    actor: deps.ActorDep,
    tickets: Annotated[object, Depends(deps.support_tickets)],
    messages: Annotated[object, Depends(deps.ticket_messages)],
) -> dict:
    row = tickets.get(ticket_id)
    is_staff = actor.role in STAFF_ROLES
    if not is_staff and row.user_id != actor.user_id:
        # The same answer as a missing ticket, so this cannot be used to
        # discover that a reference exists.
        raise NotFoundError(error_codes.TICKET_NOT_FOUND, id=ticket_id)
    return ok(
        _ticket_out(row, messages.for_ticket(row.id), to_staff=is_staff).model_dump()
    )


@router.post("/support/tickets/{ticket_id}/messages", status_code=201)
def reply(
    ticket_id: str,
    body: ReplyIn,
    actor: deps.ActorDep,
    tickets: Annotated[object, Depends(deps.support_tickets)],
    messages: Annotated[object, Depends(deps.ticket_messages)],
    notifier: Annotated[object, Depends(deps.notifier)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    use_case = ReplyToTicket(
        tickets=tickets, messages=messages, audit=audit, notifier=notifier,
        clock=deps.clock(), new_id=deps.new_id,
    )
    status = use_case.execute(
        ReplyCommand(
            ticket_id=ticket_id,
            actor_id=actor.user_id,
            actor_role=actor.role,
            body=body.body,
            is_internal=body.is_internal,
        )
    )
    return ok({"ticket_id": ticket_id, "status": status.value})


# -- the operator's side ------------------------------------------------

@router.get("/admin/support/tickets")
def queue(
    actor: Annotated[deps.Actor, Depends(deps.require_support)],
    tickets: Annotated[object, Depends(deps.support_tickets)],
    messages: Annotated[object, Depends(deps.ticket_messages)],
    status: str | None = None,
    category: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict:
    """Urgent first, then oldest.

    The ordering is the triage. Nobody is watching overnight, so a safety
    report raised at 02:00 must not be pushed down the page by a fare dispute
    raised at 09:00 -- there is no human awake to notice it happening.
    """
    rows = tickets.queue(status=status, category=category, limit=limit)
    return ok(
        {
            "tickets": [
                _ticket_out(row, messages.for_ticket(row.id), to_staff=True).model_dump()
                for row in rows
            ],
            "open": tickets.open_count(),
            "urgent_open": tickets.open_count(urgent_only=True),
        }
    )


@router.post("/admin/support/tickets/{ticket_id}/decide")
def decide(
    ticket_id: str,
    body: DecideTicketIn,
    actor: Annotated[deps.Actor, Depends(deps.require_support)],
    tickets: Annotated[object, Depends(deps.support_tickets)],
    messages: Annotated[object, Depends(deps.ticket_messages)],
    notifier: Annotated[object, Depends(deps.notifier)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    use_case = DecideTicket(
        tickets=tickets, messages=messages, audit=audit, notifier=notifier,
        clock=deps.clock(),
    )
    status = use_case.execute(
        DecideTicketCommand(
            ticket_id=ticket_id,
            actor_id=actor.user_id,
            actor_role=actor.role,
            target=TicketStatus(body.status),
        )
    )
    return ok({"ticket_id": ticket_id, "status": status.value})
