"""Ratings, idempotency and support repositories."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from infrastructure.db.models.ops import (
    CancellationRow,
    IdempotencyRow,
    ImportJobRow,
    NotificationRow,
    RatingRow,
    SupportTicketRow,
)
from infrastructure.db.repositories.base import SqlRepository
from shared import error_codes


class RatingRepository(SqlRepository[RatingRow]):
    model = RatingRow
    not_found_code = error_codes.TRIP_NOT_FOUND

    def find(self, trip_id: str, rater_user_id: str, ratee_user_id: str) -> RatingRow | None:
        stmt = self._base().where(
            RatingRow.trip_id == trip_id,
            RatingRow.rater_user_id == rater_user_id,
            RatingRow.ratee_user_id == ratee_user_id,
        )
        return self.session.scalars(stmt).one_or_none()

    def create(self, **fields) -> RatingRow:
        row = RatingRow(**fields)
        self.session.add(row)
        return row


class CancellationRepository(SqlRepository[CancellationRow]):
    model = CancellationRow
    not_found_code = error_codes.BOOKING_NOT_FOUND

    def create(self, **fields) -> CancellationRow:
        row = CancellationRow(**fields)
        self.session.add(row)
        return row

    def by_booking_ids(self, booking_ids) -> list[CancellationRow]:
        wanted = [i for i in set(booking_ids) if i]
        if not wanted:
            return []
        return list(
            self.session.scalars(
                self._base().where(CancellationRow.booking_id.in_(wanted))
            ).all()
        )


class NotificationRepository(SqlRepository[NotificationRow]):
    model = NotificationRow
    not_found_code = error_codes.USER_NOT_FOUND

    def create(self, **fields) -> NotificationRow:
        row = NotificationRow(**fields)
        self.session.add(row)
        return row

    def for_user(self, user_id: str, *, limit: int = 30):
        stmt = (
            self._base()
            .where(NotificationRow.user_id == user_id)
            .order_by(NotificationRow.created_at.desc())
            .limit(min(limit, 100))
        )
        return list(self.session.scalars(stmt).all())


class IdempotencyRepository(SqlRepository[IdempotencyRow]):
    """Offline clients retry; assume every mutation arrives more than once."""

    model = IdempotencyRow
    not_found_code = error_codes.IDEMPOTENCY_KEY_REUSED

    def find(self, key: str, endpoint: str) -> IdempotencyRow | None:
        stmt = select(IdempotencyRow).where(
            IdempotencyRow.key == key, IdempotencyRow.endpoint == endpoint
        )
        return self.session.scalars(stmt).one_or_none()

    def remember(self, **fields) -> IdempotencyRow:
        row = IdempotencyRow(**fields)
        self.session.add(row)
        return row

    def purge_expired(self, *, at: datetime) -> int:
        result = self.session.execute(
            IdempotencyRow.__table__.delete().where(IdempotencyRow.expires_at < at)
        )
        return int(result.rowcount or 0)


class ImportJobRepository(SqlRepository[ImportJobRow]):
    """One master-data import run, with its report kept.

    The report is why this table exists: months later, the question is not
    "did the import work" but "where did this village come from".
    """

    model = ImportJobRow
    not_found_code = error_codes.IMPORT_ROW_INVALID

    def create(self, **fields) -> ImportJobRow:
        row = ImportJobRow(**fields)
        self.session.add(row)
        return row

    def recent(self, *, entity: str | None = None, limit: int = 20):
        stmt = self._base().order_by(ImportJobRow.created_at.desc()).limit(min(limit, 100))
        if entity:
            stmt = stmt.where(ImportJobRow.entity == entity)
        return list(self.session.scalars(stmt).all())


class SupportTicketRepository(SqlRepository[SupportTicketRow]):
    model = SupportTicketRow
    not_found_code = error_codes.TICKET_NOT_FOUND

    def create(self, **fields) -> SupportTicketRow:
        row = SupportTicketRow(**fields)
        self.session.add(row)
        return row
