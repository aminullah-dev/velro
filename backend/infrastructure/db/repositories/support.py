"""Support tickets and their messages."""

from __future__ import annotations

from sqlalchemy import func, select

from domain.enums import TicketStatus
from domain.support import URGENT_CATEGORIES
from infrastructure.db.models.ops import SupportTicketRow, TicketMessageRow
from infrastructure.db.repositories.base import SqlRepository
from shared import error_codes

#: The value a caller passes to mean "no status filter at all".
ANY_STATUS = "ALL"


class SupportTicketRepository(SqlRepository[SupportTicketRow]):
    model = SupportTicketRow
    not_found_code = error_codes.TICKET_NOT_FOUND

    def create(self, **fields) -> SupportTicketRow:
        row = SupportTicketRow(**fields)
        self.session.add(row)
        return row

    def find_by_reference(self, reference: str) -> SupportTicketRow | None:
        return self.find_by(reference=reference)

    def for_user(self, user_id: str, *, limit: int = 30) -> list[SupportTicketRow]:
        stmt = (
            self._base()
            .where(SupportTicketRow.user_id == user_id)
            .order_by(SupportTicketRow.created_at.desc())
            .limit(min(limit, 100))
        )
        return list(self.session.scalars(stmt).all())

    def queue(
        self, *, status: str | None = None, category: str | None = None, limit: int = 50
    ) -> list[SupportTicketRow]:
        """The operator's queue: urgent first, then oldest.

        Urgent before recent, deliberately. A safety report raised at 02:00 must
        not be pushed down the page by a fare dispute raised at 09:00 -- the
        ordering *is* the triage, because there is nobody watching overnight to
        do it by hand.
        """
        urgency = func.coalesce(
            SupportTicketRow.category_code.in_(sorted(URGENT_CATEGORIES)), False
        )
        stmt = self._base().order_by(urgency.desc(), SupportTicketRow.created_at)

        if status == ANY_STATUS:
            # Everything, including answered and closed. Asked for explicitly,
            # because the default below is a working queue and not an archive --
            # and a client that wanted "all" and simply omitted the filter was
            # silently given the queue instead, which is how a panel ends up
            # telling an operator a report was never raised.
            pass
        elif status:
            stmt = stmt.where(SupportTicketRow.status == status)
        else:
            stmt = stmt.where(
                SupportTicketRow.status.in_(
                    (TicketStatus.OPEN.value, TicketStatus.IN_PROGRESS.value)
                )
            )
        if category:
            stmt = stmt.where(SupportTicketRow.category_code == category)

        return list(self.session.scalars(stmt.limit(min(limit, 200))).all())

    def open_count(self, *, urgent_only: bool = False) -> int:
        stmt = (
            select(func.count())
            .select_from(SupportTicketRow)
            .where(
                SupportTicketRow.deleted_at.is_(None),
                SupportTicketRow.status.in_(
                    (TicketStatus.OPEN.value, TicketStatus.IN_PROGRESS.value)
                ),
            )
        )
        if urgent_only:
            stmt = stmt.where(
                SupportTicketRow.category_code.in_(sorted(URGENT_CATEGORIES))
            )
        return int(self.session.scalar(stmt) or 0)


class TicketMessageRepository(SqlRepository[TicketMessageRow]):
    model = TicketMessageRow
    not_found_code = error_codes.TICKET_NOT_FOUND

    def create(self, **fields) -> TicketMessageRow:
        row = TicketMessageRow(**fields)
        self.session.add(row)
        return row

    def for_ticket(self, ticket_id: str) -> list[TicketMessageRow]:
        """Oldest first: a conversation reads forwards."""
        stmt = (
            self._base()
            .where(TicketMessageRow.ticket_id == ticket_id)
            .order_by(TicketMessageRow.created_at)
        )
        return list(self.session.scalars(stmt).all())
