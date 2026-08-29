"""Raising a support request, and answering one.

Two audiences with different rights over the same rows: the person who raised
it, who may read and reply, and staff, who may also assign, resolve, close and
write notes the other party never sees.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass

from domain.enums import ActorRole, TicketStatus
from domain.support import MAX_BODY, MAX_SUBJECT, SupportTicket, TicketMessage
from shared import error_codes
from shared.clock import Clock
from shared.errors import NotFoundError, PermissionError, ValidationError
from shared.ids import IdGenerator

STAFF_ROLES = frozenset({ActorRole.DISPATCHER, ActorRole.ADMIN, ActorRole.SYSTEM})


@dataclass(frozen=True, slots=True)
class RaiseTicketCommand:
    user_id: str
    actor_role: ActorRole
    category_code: str
    subject: str
    body: str
    trip_id: str | None = None
    booking_id: str | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class RaisedTicket:
    id: str
    reference: str
    status: TicketStatus
    is_urgent: bool


class RaiseTicket:
    def __init__(
        self, *, tickets, messages, numbers, audit, notifier=None,
        clock: Clock, new_id: IdGenerator,
    ) -> None:
        self._tickets = tickets
        self._messages = messages
        self._numbers = numbers
        self._audit = audit
        self._notifier = notifier
        self._clock = clock
        self._new_id = new_id

    def execute(self, cmd: RaiseTicketCommand) -> RaisedTicket:
        now = self._clock.now()

        subject = cmd.subject.strip()[:MAX_SUBJECT]
        body = cmd.body.strip()[:MAX_BODY]
        if not body:
            raise ValidationError(error_codes.VALIDATION_FAILED, field="body", rule="empty")

        # Built first so the domain rejects an unknown category before a
        # reference number is burned on it. References are gap-free within a
        # year; spending one on a request that then fails leaves a hole an
        # auditor will ask about.
        ticket = SupportTicket(
            id=self._new_id(),
            reference="",
            user_id=cmd.user_id,
            category_code=cmd.category_code,
            subject=subject or cmd.category_code,
            trip_id=cmd.trip_id,
            booking_id=cmd.booking_id,
        )
        ticket.reference = self._numbers.allocate("ticket", year=now.year)

        row = self._tickets.create(
            id=ticket.id,
            reference=ticket.reference,
            user_id=ticket.user_id,
            category_code=ticket.category_code,
            subject=ticket.subject,
            status=TicketStatus.OPEN.value,
            trip_id=ticket.trip_id,
            booking_id=ticket.booking_id,
            created_by=cmd.user_id,
        )
        self._tickets.flush()

        self._messages.create(
            id=self._new_id(),
            ticket_id=row.id,
            author_user_id=cmd.user_id,
            author_role=cmd.actor_role.value,
            body=body,
            is_internal=False,
            created_by=cmd.user_id,
        )

        self._audit.write(
            "support.ticket_raised",
            actor_id=cmd.user_id,
            actor_role=cmd.actor_role,
            entity_type="support_ticket",
            entity_id=row.id,
            after={
                "reference": ticket.reference,
                "category_code": ticket.category_code,
                "urgent": ticket.is_urgent,
                "trip_id": ticket.trip_id,
                # The body is deliberately absent. It may describe an assault.
            },
            request_id=cmd.request_id,
        )

        # Told back to the person who raised it, so the reference exists
        # somewhere they can find it again -- including on a phone that has
        # since lost the screen they typed it on.
        _tell(
            self._notifier,
            user_id=cmd.user_id,
            message_key="notify.support.received",
            payload={"reference": ticket.reference},
        )
        return RaisedTicket(
            id=row.id,
            reference=ticket.reference,
            status=TicketStatus.OPEN,
            is_urgent=ticket.is_urgent,
        )


@dataclass(frozen=True, slots=True)
class ReplyCommand:
    ticket_id: str
    actor_id: str
    actor_role: ActorRole
    #: Decided by the caller from the actor's real roles, not inferred here.
    #:
    #: ActorRole collapses six staff roles into two, so `actor_role in
    #: STAFF_ROLES` hands a finance manager the same powers over a safety
    #: report as a support agent.
    is_staff: bool
    body: str
    is_internal: bool = False
    request_id: str | None = None


class ReplyToTicket:
    def __init__(
        self, *, tickets, messages, audit, notifier=None, clock: Clock, new_id: IdGenerator
    ) -> None:
        self._tickets = tickets
        self._messages = messages
        self._audit = audit
        self._notifier = notifier
        self._clock = clock
        self._new_id = new_id

    def execute(self, cmd: ReplyCommand) -> TicketStatus:
        now = self._clock.now()
        row = self._tickets.get(cmd.ticket_id)
        is_staff = cmd.is_staff

        if not is_staff and row.user_id != cmd.actor_id:
            # The same answer as a missing ticket, so the endpoint cannot be
            # used to discover that a reference exists.
            raise NotFoundError(error_codes.TICKET_NOT_FOUND, id=cmd.ticket_id)
        if cmd.is_internal and not is_staff:
            raise PermissionError(error_codes.PERMISSION_DENIED, action="support.internal_note")

        ticket = to_ticket(row, self._messages.for_ticket(row.id))
        message = TicketMessage(
            id=self._new_id(),
            ticket_id=row.id,
            author_user_id=cmd.actor_id,
            author_role=cmd.actor_role,
            body=cmd.body.strip()[:MAX_BODY],
            is_internal=cmd.is_internal,
            sent_at=now,
        )
        # The domain decides whether this reply reopens the ticket.
        ticket.add_message(message)

        self._messages.create(
            id=message.id,
            ticket_id=row.id,
            author_user_id=message.author_user_id,
            author_role=message.author_role.value,
            body=message.body,
            is_internal=message.is_internal,
            created_by=cmd.actor_id,
        )
        if row.status != ticket.status.value:
            row.status = ticket.status.value
            row.resolved_at = ticket.resolved_at
            self._tickets.save(row)

        self._audit.write(
            "support.ticket_replied",
            actor_id=cmd.actor_id,
            actor_role=cmd.actor_role,
            entity_type="support_ticket",
            entity_id=row.id,
            after={"status": ticket.status.value, "internal": cmd.is_internal},
            request_id=cmd.request_id,
        )

        # Only the other party is told, and never about an internal note.
        if not cmd.is_internal and is_staff:
            _tell(
                self._notifier,
                user_id=row.user_id,
                message_key="notify.support.answered",
                payload={"reference": row.reference},
            )
        return ticket.status


@dataclass(frozen=True, slots=True)
class DecideTicketCommand:
    ticket_id: str
    actor_id: str
    actor_role: ActorRole
    is_staff: bool
    target: TicketStatus
    request_id: str | None = None


class DecideTicket:
    """Staff move a request along. Only staff."""

    def __init__(self, *, tickets, messages, audit, notifier=None, clock: Clock) -> None:
        self._tickets = tickets
        self._messages = messages
        self._audit = audit
        self._notifier = notifier
        self._clock = clock

    def execute(self, cmd: DecideTicketCommand) -> TicketStatus:
        if not cmd.is_staff:
            raise PermissionError(error_codes.PERMISSION_DENIED, action="support.decide")

        now = self._clock.now()
        row = self._tickets.get(cmd.ticket_id)
        ticket = to_ticket(row, self._messages.for_ticket(row.id))
        before = ticket.status

        ticket.transition_to(cmd.target, at=now, by=cmd.actor_id)

        row.status = ticket.status.value
        row.resolved_at = ticket.resolved_at
        row.assigned_to = ticket.assigned_to
        self._tickets.save(row)

        self._audit.write(
            f"support.ticket_{cmd.target.value.lower()}",
            actor_id=cmd.actor_id,
            actor_role=cmd.actor_role,
            entity_type="support_ticket",
            entity_id=row.id,
            before={"status": before.value},
            after={"status": ticket.status.value},
            request_id=cmd.request_id,
        )
        if cmd.target is TicketStatus.RESOLVED:
            _tell(
                self._notifier,
                user_id=row.user_id,
                message_key="notify.support.resolved",
                payload={"reference": row.reference},
            )
        return ticket.status


def to_ticket(row, message_rows) -> SupportTicket:
    return SupportTicket(
        id=row.id,
        reference=row.reference,
        user_id=row.user_id,
        category_code=row.category_code,
        subject=row.subject,
        status=TicketStatus(row.status),
        trip_id=row.trip_id,
        booking_id=row.booking_id,
        assigned_to=row.assigned_to,
        resolved_at=row.resolved_at,
        messages=[
            TicketMessage(
                id=m.id,
                ticket_id=m.ticket_id,
                author_user_id=m.author_user_id,
                author_role=ActorRole(m.author_role),
                body=m.body,
                is_internal=m.is_internal,
                sent_at=m.created_at,
            )
            for m in message_rows
        ],
    )


def _tell(notifier, **kwargs) -> None:
    """Best effort. A request that was raised stays raised whatever happens
    to the message announcing it."""
    if notifier is None:
        return
    with contextlib.suppress(Exception):
        notifier.notify(**kwargs)
