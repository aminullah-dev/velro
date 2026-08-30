"""Support requests.

Somebody with a problem and nobody to ask. The rules here are small: what a
request may say, who may add to it, and how it moves. What makes it useful
lives elsewhere -- in whether an operator sees it in time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from domain.enums import ActorRole, TicketStatus
from domain.lifecycles import TICKET_LIFECYCLE
from shared import error_codes
from shared.errors import ConflictError, ValidationError

# What a request can be about. Codes, not sentences: each resolves to a
# translated label, and an operator filters on the code.
CATEGORIES: frozenset[str] = frozenset(
    {
        "SAFETY",          # the one that jumps the queue
        "LOST_ITEM",
        "FARE_DISPUTE",
        "DRIVER_CONDUCT",
        "PASSENGER_CONDUCT",
        "VEHICLE_CONDITION",
        "APP_PROBLEM",
        "OTHER",
    }
)

# A safety report is not a support request with a different label on it: it is
# the reason the queue is sorted at all.
URGENT_CATEGORIES: frozenset[str] = frozenset({"SAFETY", "DRIVER_CONDUCT", "PASSENGER_CONDUCT"})

MAX_SUBJECT = 200
MAX_BODY = 4000


@dataclass(slots=True)
class TicketMessage:
    id: str
    ticket_id: str
    author_user_id: str
    author_role: ActorRole
    body: str
    is_internal: bool = False
    sent_at: datetime | None = None


@dataclass(slots=True)
class SupportTicket:
    id: str
    reference: str
    user_id: str
    category_code: str
    subject: str
    status: TicketStatus = TicketStatus.OPEN
    trip_id: str | None = None
    booking_id: str | None = None
    assigned_to: str | None = None
    resolved_at: datetime | None = None
    messages: list[TicketMessage] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.category_code not in CATEGORIES:
            raise ValidationError(
                error_codes.VALIDATION_FAILED,
                field="category_code",
                value=self.category_code,
                allowed=sorted(CATEGORIES),
            )
        if not self.subject.strip():
            raise ValidationError(error_codes.VALIDATION_FAILED, field="subject", rule="empty")

    @property
    def is_urgent(self) -> bool:
        return self.category_code in URGENT_CATEGORIES

    @property
    def is_open(self) -> bool:
        return self.status in (TicketStatus.OPEN, TicketStatus.IN_PROGRESS)

    def assert_can_be_added_to(self) -> None:
        """A closed request takes no more messages.

        Reopening exists for that -- and it is deliberately a different action,
        because a request answered weeks ago and one still being worked on need
        to be told apart by whoever is looking at the queue.
        """
        if self.status is TicketStatus.CLOSED:
            raise ConflictError(error_codes.TICKET_CLOSED, ticket_id=self.id)

    def add_message(self, message: TicketMessage) -> None:
        self.assert_can_be_added_to()
        if not message.body.strip():
            raise ValidationError(error_codes.VALIDATION_FAILED, field="body", rule="empty")

        # A reply from the person who raised it pulls a resolved request back
        # open. An operator marking something fixed is a claim; this is the
        # only party who knows whether it was.
        from_reporter = message.author_user_id == self.user_id
        if (
            self.status is TicketStatus.RESOLVED
            and from_reporter
            and not message.is_internal
        ):
            self.status = TicketStatus.IN_PROGRESS
            self.resolved_at = None

        # And an answer from staff means somebody has looked. Without this the
        # app showed VELRO's reply above the words "Not read yet", which reads
        # as nobody having seen it -- on the screen of a person waiting to hear
        # that somebody had.
        if (
            self.status is TicketStatus.OPEN
            and not from_reporter
            and not message.is_internal
        ):
            self.status = TicketStatus.IN_PROGRESS

        self.messages.append(message)

    def transition_to(self, target: TicketStatus, *, at: datetime, by: str | None = None) -> None:
        TICKET_LIFECYCLE.check(self.status, target, ticket_id=self.id)
        self.status = target
        if target is TicketStatus.RESOLVED:
            self.resolved_at = at
        elif target is TicketStatus.IN_PROGRESS:
            self.resolved_at = None
            if by is not None:
                self.assigned_to = by

    def visible_messages(self, *, to_staff: bool) -> list[TicketMessage]:
        """Internal notes never reach the person who raised the request.

        Operators need somewhere to write "this driver has three of these", and
        that somewhere must not be the thread the driver is reading.
        """
        if to_staff:
            return list(self.messages)
        return [m for m in self.messages if not m.is_internal]
