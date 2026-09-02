"""Ratings, idempotency and support repositories."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update

from infrastructure.db.models.ops import (
    CancellationRow,
    DeviceTokenRow,
    IdempotencyRow,
    ImportJobRow,
    NotificationRow,
    RatingRow,
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

    def unread_count(self, user_id: str) -> int:
        return int(
            self.session.scalar(
                select(func.count())
                .select_from(NotificationRow)
                .where(
                    NotificationRow.user_id == user_id,
                    NotificationRow.read_at.is_(None),
                    NotificationRow.deleted_at.is_(None),
                )
            )
            or 0
        )

    def mark_read(self, user_id: str, *, at: datetime, ids=None) -> int:
        """Mark everything, or just what was named.

        Scoped to the caller's own rows: an id from someone else's inbox does
        nothing rather than marking their notification read.
        """
        stmt = update(NotificationRow).where(
            NotificationRow.user_id == user_id,
            NotificationRow.read_at.is_(None),
            NotificationRow.deleted_at.is_(None),
        )
        wanted = [i for i in (ids or []) if i]
        if wanted:
            stmt = stmt.where(NotificationRow.id.in_(wanted))
        return int(self.session.execute(stmt.values(read_at=at)).rowcount or 0)

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

    def find(self, key: str, endpoint: str, *, user_id: str) -> IdempotencyRow | None:
        """The stored answer for this user's key on this endpoint, if any.

        ``user_id`` is required, not optional: a lookup that could match any
        user's row would hand one account another's stored response. A row
        with no user (written before the scope existed) matches nobody and
        simply expires.
        """
        stmt = select(IdempotencyRow).where(
            IdempotencyRow.user_id == user_id,
            IdempotencyRow.key == key,
            IdempotencyRow.endpoint == endpoint,
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


class DeviceTokenRepository(SqlRepository[DeviceTokenRow]):
    """Where a push actually goes.

    A person has one token per device per app, and phones are shared and
    reinstalled -- so registering is an upsert on the token itself, and a token
    that reappears under a different user moves rather than duplicating. Sending
    a driver's ride offer to whoever had the handset last is the failure this
    prevents.
    """

    model = DeviceTokenRow
    not_found_code = error_codes.USER_NOT_FOUND

    def register(
        self, *, id: str, user_id: str, token: str, platform: str, app: str,
        device_id: str | None, locale: str | None, at: datetime,
    ) -> DeviceTokenRow:
        row = self.session.scalars(
            self._base().where(DeviceTokenRow.token == token)
        ).first()
        if row is None:
            row = DeviceTokenRow(
                id=id, user_id=user_id, token=token, platform=platform,
                app=app, device_id=device_id, locale=locale, last_seen_at=at,
            )
            self.session.add(row)
            self.session.flush()
            return row
        row.user_id = user_id
        row.platform = platform
        row.app = app
        row.device_id = device_id
        row.locale = locale
        row.last_seen_at = at
        row.version += 1
        self.session.add(row)
        return row

    def for_users(self, user_ids, *, app: str | None = None) -> list[DeviceTokenRow]:
        wanted = [i for i in set(user_ids) if i]
        if not wanted:
            return []
        stmt = self._base().where(DeviceTokenRow.user_id.in_(wanted))
        if app:
            stmt = stmt.where(DeviceTokenRow.app == app)
        return list(self.session.scalars(stmt).all())

    def forget(self, token: str) -> int:
        """Drop a token the push service says is dead.

        Kept as a hard delete: a stale token is not history, it is an address
        that no longer exists, and keeping it means retrying it for ever.
        """
        return int(
            self.session.execute(
                DeviceTokenRow.__table__.delete().where(DeviceTokenRow.token == token)
            ).rowcount
            or 0
        )
