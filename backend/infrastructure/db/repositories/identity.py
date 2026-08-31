"""Identity repositories."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update

from domain.enums import UserStatus
from infrastructure.db.models.identity import (
    OtpChallengeRow,
    RefreshTokenRow,
    RoleRow,
    UserRoleRow,
    UserRow,
)
from infrastructure.db.repositories.base import SqlRepository
from shared import error_codes
from shared.ids import new_id


class UserRepository(SqlRepository[UserRow]):
    model = UserRow
    not_found_code = error_codes.USER_NOT_FOUND

    def get_many(self, ids: list[str]) -> list[UserRow]:
        """Several users in one query.

        A manifest names every passenger on a shared trip, and a lookup per row
        is how a screen on a valley connection becomes a screen that never
        finishes loading.
        """
        if not ids:
            return []
        return list(self.session.scalars(self._base().where(UserRow.id.in_(ids))).all())

    def find_by_phone(self, phone: str) -> UserRow | None:
        return self.find_by(phone=phone)

    def create(
        self, *, id: str, phone: str, locale: str, full_name: str | None = None
    ) -> UserRow:
        """Create a user with every column populated.

        The status is set here rather than left to the column default. A
        SQLAlchemy default is applied at flush, so anything reading the attribute
        between construction and flush sees None -- and the sign-in path reads
        it immediately to check the account is active. That made the very first
        request a brand-new user ever makes return a 500, which is the one
        request that must not.
        """
        row = UserRow(
            id=id,
            phone=phone,
            locale=locale,
            full_name=full_name,
            status=UserStatus.ACTIVE.value,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def roles_of(self, user_id: str) -> list[str]:
        stmt = (
            select(RoleRow.code)
            .join(UserRoleRow, UserRoleRow.role_id == RoleRow.id)
            .where(
                UserRoleRow.user_id == user_id,
                UserRoleRow.deleted_at.is_(None),
                RoleRow.deleted_at.is_(None),
            )
        )
        return list(self.session.scalars(stmt).all())

    def grant_role(self, user_id: str, role_code: str) -> None:
        role = self.session.scalars(
            select(RoleRow).where(RoleRow.code == role_code, RoleRow.deleted_at.is_(None))
        ).one()
        existing = self.session.scalars(
            select(UserRoleRow).where(
                UserRoleRow.user_id == user_id,
                UserRoleRow.role_id == role.id,
                UserRoleRow.deleted_at.is_(None),
            )
        ).one_or_none()
        if existing is None:
            self.session.add(UserRoleRow(id=new_id(), user_id=user_id, role_id=role.id))

    def record_rating(self, user_id: str, score: int) -> None:
        """Add one score a driver gave this passenger.

        The same shape as DriverRepository.record_rating, and deliberately so:
        two ways of keeping the same kind of average is two places for it to be
        wrong differently.
        """
        row = self.get(user_id)
        row.rating_sum += score
        row.rating_count += 1
        row.version += 1
        self.session.add(row)


class OtpRepository(SqlRepository[OtpChallengeRow]):
    model = OtpChallengeRow
    not_found_code = error_codes.OTP_INVALID

    def create(self, **fields) -> OtpChallengeRow:
        row = OtpChallengeRow(**fields)
        self.session.add(row)
        return row

    def find_active(self, phone: str, *, at: datetime) -> OtpChallengeRow | None:
        """The most recent unconsumed, unexpired challenge for this number."""
        stmt = (
            self._base()
            .where(
                OtpChallengeRow.phone == phone,
                OtpChallengeRow.consumed_at.is_(None),
                OtpChallengeRow.expires_at > at,
            )
            .order_by(OtpChallengeRow.created_at.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).one_or_none()

    def count_recent(self, phone: str, *, since: datetime) -> int:
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(OtpChallengeRow)
            .where(
                OtpChallengeRow.phone == phone,
                OtpChallengeRow.created_at >= since,
                OtpChallengeRow.deleted_at.is_(None),
            )
        )
        return int(self.session.scalar(stmt) or 0)


class RefreshTokenRepository(SqlRepository[RefreshTokenRow]):
    model = RefreshTokenRow
    not_found_code = error_codes.TOKEN_INVALID

    def create(self, **fields) -> RefreshTokenRow:
        row = RefreshTokenRow(**fields)
        self.session.add(row)
        return row

    def find_by_hash(self, token_hash: str) -> RefreshTokenRow | None:
        return self.find_by(token_hash=token_hash)

    def revoke_all_for_user(self, user_id: str, *, at: datetime) -> int:
        """'Log out all devices'. Real because the token is server-side."""
        result = self.session.execute(
            update(RefreshTokenRow)
            .where(
                RefreshTokenRow.user_id == user_id,
                RefreshTokenRow.revoked_at.is_(None),
            )
            .values(revoked_at=at, version=RefreshTokenRow.version + 1)
        )
        return int(result.rowcount or 0)
