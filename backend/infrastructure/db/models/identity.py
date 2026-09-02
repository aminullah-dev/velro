from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from domain.enums import Locale, UserStatus
from infrastructure.db.base import Auditable, Base, enum_check


class UserRow(Auditable, Base):
    __tablename__ = "users"

    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(160))
    locale: Mapped[str] = mapped_column(String(8), default=Locale.DARI.value, nullable=False)
    photo_key: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), default=UserStatus.ACTIVE.value, nullable=False)
    #: A passenger's standing, as sum and count rather than an average, so it
    #: can be corrected exactly rather than drifting. Mirrors the driver row.
    rating_sum: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rating_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: For the staff console's sign-in code, and nothing else. The phone is
    #: the identity; this is a second pipe the code may travel down, and it
    #: is empty on almost every row -- most of Ghorband has no inbox.
    email: Mapped[str | None] = mapped_column(String(254))

    __table_args__ = (
        # Uniqueness that matters to the business is a database constraint, not
        # an application check: two sign-ups a microsecond apart both pass an
        # application check and only one may win.
        UniqueConstraint("phone", name="uq_users_phone"),
        # Partial: nulls are the common case and must not collide.
        Index(
            "uq_users_email", "email", unique=True,
            postgresql_where=text("email IS NOT NULL"),
            sqlite_where=text("email IS NOT NULL"),
        ),
        enum_check("status", UserStatus, name="users_status"),
        enum_check("locale", Locale, name="users_locale"),
    )


class RoleRow(Auditable, Base):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name_key: Mapped[str] = mapped_column(String(80), nullable=False)
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (UniqueConstraint("code", name="uq_roles_code"),)


class PermissionRow(Auditable, Base):
    __tablename__ = "permissions"

    # The permission name matches the audit action name, deliberately, so a
    # support question about who could have done something has one answer.
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    description_key: Mapped[str] = mapped_column(String(120), nullable=False)

    __table_args__ = (UniqueConstraint("code", name="uq_permissions_code"),)


class RolePermissionRow(Auditable, Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    permission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("permissions.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    __table_args__ = (
        UniqueConstraint(
            "role_id", "permission_id", name="uq_role_permissions_role_id_permission_id"
        ),
    )


class UserRoleRow(Auditable, Base):
    __tablename__ = "user_roles"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    __table_args__ = (UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_id_role_id"),)


class OtpChallengeRow(Auditable, Base):
    __tablename__ = "otp_challenges"

    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_ip: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (Index("ix_otp_challenges_phone_expires_at", "phone", "expires_at"),)


class RefreshTokenRow(Auditable, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(128), index=True)
    user_agent: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[str | None] = mapped_column(String(36))

    __table_args__ = (UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),)
