from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from domain.enums import ActorRole, ImportStatus, TicketStatus
from infrastructure.db.base import Auditable, Base, enum_check


class SettingRow(Auditable, Base):
    """Everything an operator may change without a deploy.

    Commission rate, cancellation policy, OTP lifetime, emergency numbers,
    booking limits, driver document requirements. Section 105: none of these is
    a constant in code.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)  # int/str/bool/json
    description_key: Mapped[str | None] = mapped_column(String(120))
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (UniqueConstraint("key", name="uq_app_settings_key"),)


class NumberSequenceRow(Auditable, Base):
    """Gap-free business numbers, allocated inside the transaction that uses them."""

    __tablename__ = "number_sequences"

    entity: Mapped[str] = mapped_column(String(24), nullable=False)   # trip / booking / settlement
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    next_value: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    padding: Mapped[int] = mapped_column(Integer, default=6, nullable=False)

    __table_args__ = (
        UniqueConstraint("entity", "year", name="uq_number_sequences_entity_year"),
        CheckConstraint("next_value > 0", name="ck_number_sequences_next_value_positive"),
    )


class AuditLogRow(Auditable, Base):
    """Append-only, never rotated, included in backups, admissible in a dispute.

    Written inside the same transaction as the change it records -- an audit
    trail that can be missing when the write succeeded is worse than none,
    because it will be trusted.
    """

    __tablename__ = "audit_logs"

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor_role: Mapped[str] = mapped_column(String(20), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)    # booking.created
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    before: Mapped[dict[str, object] | None] = mapped_column(JSON)
    after: Mapped[dict[str, object] | None] = mapped_column(JSON)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)    # api / admin / job / sync
    request_id: Mapped[str | None] = mapped_column(String(36), index=True)
    ip_address: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        Index("ix_audit_logs_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_audit_logs_action_occurred_at", "action", "occurred_at"),
        enum_check("actor_role", ActorRole, name="audit_logs_actor_role"),
    )


class IdempotencyRow(Auditable, Base):
    """Offline clients retry; assume every mutation arrives more than once.

    The key plus a hash of the request body plus the stored response. A repeat
    with the same key returns the stored response; a repeat with the same key
    and a different body is a client bug and returns 409.
    """

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    endpoint: Mapped[str] = mapped_column(String(120), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, object] | None] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("key", "endpoint", name="uq_idempotency_keys_key_endpoint"),
        Index("ix_idempotency_keys_expires_at", "expires_at"),
    )


class RatingRow(Auditable, Base):
    __tablename__ = "ratings"

    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    booking_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("bookings.id", ondelete="RESTRICT"), index=True
    )
    rater_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ratee_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    rater_role: Mapped[str] = mapped_column(String(20), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        # One rating per person per trip, in each direction.
        UniqueConstraint(
            "trip_id", "rater_user_id", "ratee_user_id",
            name="uq_ratings_trip_id_rater_user_id_ratee_user_id",
        ),
        CheckConstraint("score >= 1 AND score <= 5", name="ck_ratings_score_range"),
        enum_check("rater_role", ActorRole, name="ratings_rater_role"),
    )


class CancellationRow(Auditable, Base):
    __tablename__ = "cancellations"

    trip_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="RESTRICT"), index=True
    )
    booking_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("bookings.id", ondelete="RESTRICT"), index=True
    )
    cancelled_by_user_id: Mapped[str | None] = mapped_column(String(36), index=True)
    cancelled_by_role: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(40), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    fee_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    fee_currency: Mapped[str] = mapped_column(String(3), default="AFN", nullable=False)

    __table_args__ = (
        CheckConstraint(
            "(trip_id IS NOT NULL) OR (booking_id IS NOT NULL)",
            name="ck_cancellations_target_present",
        ),
        CheckConstraint("fee_minor >= 0", name="ck_cancellations_fee_non_negative"),
        enum_check("cancelled_by_role", ActorRole, name="cancellations_cancelled_by_role"),
    )


class NotificationRow(Auditable, Base):
    __tablename__ = "notifications"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # A key plus a payload, never a rendered sentence: the device renders it in
    # the locale the user is actually reading.
    message_key: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    channel: Mapped[str] = mapped_column(String(12), nullable=False)   # PUSH / SMS / IN_APP
    trip_id: Mapped[str | None] = mapped_column(String(36), index=True)
    booking_id: Mapped[str | None] = mapped_column(String(36), index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_status: Mapped[str] = mapped_column(String(16), default="PENDING", nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_notifications_user_id_created_at", "user_id", "created_at"),
        Index("ix_notifications_delivery_status", "delivery_status"),
    )


class DeviceTokenRow(Auditable, Base):
    __tablename__ = "device_tokens"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    token: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(12), nullable=False)   # ANDROID / IOS / WEB
    device_id: Mapped[str | None] = mapped_column(String(128))
    app: Mapped[str] = mapped_column(String(16), nullable=False)        # PASSENGER / DRIVER
    locale: Mapped[str | None] = mapped_column(String(8))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("token", name="uq_device_tokens_token"),)


class SupportTicketRow(Auditable, Base):
    __tablename__ = "support_tickets"

    reference: Mapped[str] = mapped_column(String(24), nullable=False)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    category_code: Mapped[str] = mapped_column(String(40), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=TicketStatus.OPEN.value, nullable=False)
    trip_id: Mapped[str | None] = mapped_column(String(36), index=True)
    booking_id: Mapped[str | None] = mapped_column(String(36), index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(36), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("reference", name="uq_support_tickets_reference"),
        Index("ix_support_tickets_status_created_at", "status", "created_at"),
        enum_check("status", TicketStatus, name="support_tickets_status"),
    )


class TicketMessageRow(Auditable, Base):
    __tablename__ = "ticket_messages"

    ticket_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("support_tickets.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    author_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    author_role: Mapped[str] = mapped_column(String(20), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_key: Mapped[str | None] = mapped_column(String(255))
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (enum_check("author_role", ActorRole, name="ticket_messages_author_role"),)


class ImportJobRow(Auditable, Base):
    """One master-data import run: validate -> duplicate-detect -> preview -> commit.

    The report is kept so that a question about where a village came from has an
    answer months later.
    """

    __tablename__ = "import_jobs"

    entity: Mapped[str] = mapped_column(String(24), nullable=False)    # villages / stations
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=ImportStatus.UPLOADED.value, nullable=False
    )
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valid_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    report: Mapped[dict[str, object] | None] = mapped_column(JSON)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (enum_check("status", ImportStatus, name="import_jobs_status"),)


class CrashReportRow(Base):
    """A handset's dying words. Written by an unauthenticated endpoint, so
    deliberately free of anything personal: no user id, no phone, no location
    -- an app name, a version, a device model and the trace."""

    __tablename__ = "crash_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    app: Mapped[str] = mapped_column(String(20), nullable=False)
    version_code: Mapped[int] = mapped_column(Integer, nullable=False)
    version_name: Mapped[str] = mapped_column(String(40), nullable=False)
    device: Mapped[str] = mapped_column(String(120), nullable=False)
    sdk: Mapped[int] = mapped_column(Integer, nullable=False)
    stack: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
