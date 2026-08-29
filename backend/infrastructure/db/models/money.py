from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from domain.enums import (
    PaymentMethod,
    PaymentStatus,
    SettlementDirection,
    SettlementStatus,
    WalletEntryKind,
)
from infrastructure.db.base import Auditable, Base, enum_check


class PaymentRow(Auditable, Base):
    __tablename__ = "payments"

    booking_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    method: Mapped[str] = mapped_column(
        String(20), default=PaymentMethod.CASH.value, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(12), default=PaymentStatus.PENDING.value, nullable=False
    )
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_currency: Mapped[str] = mapped_column(String(3), default="AFN", nullable=False)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_by: Mapped[str | None] = mapped_column(String(36))
    # Kept for the day a provider is added; unused while everything is cash.
    provider_reference: Mapped[str | None] = mapped_column(String(120))

    __table_args__ = (
        UniqueConstraint("booking_id", name="uq_payments_booking_id"),
        CheckConstraint("amount_minor >= 0", name="ck_payments_amount_non_negative"),
        enum_check("method", PaymentMethod, name="payments_method"),
        enum_check("status", PaymentStatus, name="payments_status"),
    )


class CommissionRow(Auditable, Base):
    """The split, stored -- not recomputed from a rate that may have changed."""

    __tablename__ = "commissions"

    booking_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    trip_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trips.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    driver_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drivers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    rate_basis_points: Mapped[int] = mapped_column(Integer, nullable=False)
    gross_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    platform_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    driver_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="AFN", nullable=False)

    __table_args__ = (
        UniqueConstraint("booking_id", name="uq_commissions_booking_id"),
        CheckConstraint(
            "rate_basis_points >= 0 AND rate_basis_points <= 10000",
            name="ck_commissions_rate_range",
        ),
        # The split must close. A commission that does not add up is a silent
        # leak, so the database refuses to store one.
        CheckConstraint(
            "platform_minor + driver_minor = gross_minor", name="ck_commissions_split_closes"
        ),
        CheckConstraint(
            "platform_minor >= 0 AND driver_minor >= 0", name="ck_commissions_parts_non_negative"
        ),
    )


class WalletRow(Auditable, Base):
    __tablename__ = "wallets"

    driver_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drivers.id", ondelete="RESTRICT"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="AFN", nullable=False)
    available_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pending_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lifetime_earned_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lifetime_commission_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lifetime_paid_minor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("driver_id", "currency", name="uq_wallets_driver_id_currency"),
    )


class WalletTransactionRow(Auditable, Base):
    """Append-only ledger. The wallet balance is a cached projection of this."""

    __tablename__ = "wallet_transactions"

    wallet_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)   # signed
    currency: Mapped[str] = mapped_column(String(3), default="AFN", nullable=False)
    balance_after_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    booking_id: Mapped[str | None] = mapped_column(String(36), index=True)
    trip_id: Mapped[str | None] = mapped_column(String(36), index=True)
    settlement_id: Mapped[str | None] = mapped_column(String(36), index=True)
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_wallet_transactions_wallet_id_created_at", "wallet_id", "created_at"),
        enum_check("kind", WalletEntryKind, name="wallet_transactions_kind"),
    )


class SettlementRow(Auditable, Base):
    __tablename__ = "settlements"

    driver_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("drivers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    wallet_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reference: Mapped[str] = mapped_column(String(24), nullable=False)
    # PAYOUT to a driver, or COLLECTION from one. Cash fares mean most
    # settlements are collections: the driver holds the fare and owes the
    # platform its share.
    direction: Mapped[str] = mapped_column(
        String(12), default=SettlementDirection.PAYOUT.value, nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    amount_minor: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="AFN", nullable=False)
    status: Mapped[str] = mapped_column(
        String(12), default=SettlementStatus.PENDING.value, nullable=False
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_by: Mapped[str | None] = mapped_column(String(36))
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("reference", name="uq_settlements_reference"),
        CheckConstraint("amount_minor >= 0", name="ck_settlements_amount_non_negative"),
        CheckConstraint("period_end >= period_start", name="ck_settlements_period_order"),
        enum_check("status", SettlementStatus, name="settlements_status"),
        enum_check("direction", SettlementDirection, name="settlements_direction"),
    )
