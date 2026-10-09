"""Identity repositories."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, text, update

from domain.enums import UserStatus
from infrastructure.db.models.identity import (
    USERS_PHONE_UNIQUE,
    OtpChallengeRow,
    RefreshTokenRow,
    RoleRow,
    UserRoleRow,
    UserRow,
)
from infrastructure.db.repositories.base import SqlRepository
from shared import error_codes
from shared.errors import NotFoundError
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

    def create_or_find(
        self, *, id: str, phone: str, locale: str, full_name: str | None = None
    ) -> tuple[UserRow, bool]:
        """The account for this number, created if there is none yet.

        Returns (row, created). Two first sign-ins for a new number used to
        both find nobody and both insert; the unique constraint on the phone
        kept one account and answered the other sign-in with a 500. The
        second insert now waits for the first to commit, is refused in a
        savepoint, and reads back the account the first one made.
        """
        row = UserRow(
            id=id,
            phone=phone,
            locale=locale,
            full_name=full_name,
            status=UserStatus.ACTIVE.value,
        )
        if self.insert_unless(row, constraint=USERS_PHONE_UNIQUE):
            return row, True
        existing = self.find_by_phone(phone)
        if existing is None:  # pragma: no cover - refused by a row nobody can see
            raise NotFoundError(self.not_found_code, phone=phone)
        return existing, False

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

    def revoke_role(self, user_id: str, role_code: str) -> bool:
        """Take a role away. The missing half of grant_role.

        Suspension is the switch for a passenger who trolls drivers; for a
        staff account gone wrong the answer was always meant to be revoking
        the role -- which nothing could do, so the answer was theoretical.

        Soft-deleted rather than deleted, like everything else here: who held
        which key and until when is exactly the question an audit asks after
        the fact. Returns whether anything was actually held.
        """
        from datetime import UTC, datetime

        role = self.session.scalars(
            select(RoleRow).where(RoleRow.code == role_code, RoleRow.deleted_at.is_(None))
        ).one()
        held = self.session.scalars(
            select(UserRoleRow).where(
                UserRoleRow.user_id == user_id,
                UserRoleRow.role_id == role.id,
                UserRoleRow.deleted_at.is_(None),
            )
        ).one_or_none()
        if held is None:
            return False
        held.deleted_at = datetime.now(UTC)
        self.session.add(held)
        return True

    def record_rating(self, user_id: str, score: int) -> None:
        """Add one score a driver gave this passenger.

        The same shape as DriverRepository.record_rating, and deliberately so:
        two ways of keeping the same kind of average is two places for it to be
        wrong differently. Added by the UPDATE itself, so two ratings that
        arrive together both count.
        """
        changed = self.session.execute(
            update(UserRow)
            .where(UserRow.id == user_id, UserRow.deleted_at.is_(None))
            .values(
                rating_sum=UserRow.rating_sum + score,
                rating_count=UserRow.rating_count + 1,
                version=UserRow.version + 1,
            )
            .execution_options(synchronize_session="fetch")
        ).rowcount
        if not changed:
            raise NotFoundError(self.not_found_code, id=user_id)


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

    def lock_phone(self, phone: str) -> None:
        """Serialise every code request for one number until this transaction ends.

        The rate limit is a count followed by an insert, and two requests
        that both count before either inserts both pass: eight simultaneous
        requests were eight SMS against a limit of three, each one paid for.
        A transaction-scoped advisory lock on the number makes the count and
        the insert one step. Keyed by the number, so it serialises only the
        requests that compete for the same limit; released by the commit or
        rollback that ends the request, so it cannot be leaked.
        """
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
            {"key": f"otp-request:{phone}"},
        )

    def reserve_attempt(self, challenge_id: str) -> int | None:
        """Spend one attempt on a challenge, atomically; the attempt number, or
        None when the challenge has none left (or was used meanwhile).

        Read-then-write lost updates: guesses that all read attempts = n all
        wrote n + 1, so twelve guesses at once were twelve evaluated guesses
        against a limit of five. The increment and the limit are one
        statement here, so PostgreSQL's row lock decides who gets the last
        attempt and nobody gets a sixth.
        """
        reserved = self.session.execute(
            update(OtpChallengeRow)
            .where(
                OtpChallengeRow.id == challenge_id,
                OtpChallengeRow.consumed_at.is_(None),
                OtpChallengeRow.attempts < OtpChallengeRow.max_attempts,
            )
            .values(
                attempts=OtpChallengeRow.attempts + 1,
                version=OtpChallengeRow.version + 1,
            )
            .returning(OtpChallengeRow.attempts)
        ).scalar_one_or_none()
        return None if reserved is None else int(reserved)

    def consume(self, challenge_id: str, *, at: datetime) -> bool:
        """Mark a challenge used, if nobody else has. False when somebody had.

        Conditional, so one code cannot sign in twice: of two requests that
        both matched it, the second waits on the first's row lock and then
        finds consumed_at already set.
        """
        claimed = self.session.execute(
            update(OtpChallengeRow)
            .where(
                OtpChallengeRow.id == challenge_id,
                OtpChallengeRow.consumed_at.is_(None),
            )
            .values(consumed_at=at, version=OtpChallengeRow.version + 1)
            .returning(OtpChallengeRow.id)
        ).scalar_one_or_none()
        return claimed is not None

    def count_recent(self, phone: str, *, since: datetime) -> int:
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

    def rotate(self, token_id: str, *, at: datetime, replaced_by_id: str) -> bool:
        """Retire a token in favour of its successor, if it is still live.

        False means somebody else retired it first -- a refresh already
        happened, or every session was ended -- and the caller must treat the
        presentation as a replay. Unconditional, two refreshes of one token
        at the same instant both succeeded and forked it into two live chains.
        """
        retired = self.session.execute(
            update(RefreshTokenRow)
            .where(RefreshTokenRow.id == token_id, RefreshTokenRow.revoked_at.is_(None))
            .values(
                revoked_at=at,
                replaced_by_id=replaced_by_id,
                version=RefreshTokenRow.version + 1,
            )
            .returning(RefreshTokenRow.id)
        ).scalar_one_or_none()
        return retired is not None

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
