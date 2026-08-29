"""Money repositories.

The wallet balance is a cached projection of an append-only ledger. Both are
written in the same transaction, and the ledger is the truth: if they ever
disagree, the ledger is right and the balance is rebuilt from it.
"""

from __future__ import annotations

from sqlalchemy import select

from infrastructure.db.models.money import (
    CommissionRow,
    PaymentRow,
    SettlementRow,
    WalletRow,
    WalletTransactionRow,
)
from infrastructure.db.repositories.base import SqlRepository
from shared import error_codes
from shared.ids import new_id


class PaymentRepository(SqlRepository[PaymentRow]):
    model = PaymentRow
    not_found_code = error_codes.PAYMENT_NOT_FOUND

    def find_for_booking(self, booking_id: str) -> PaymentRow | None:
        return self.find_by(booking_id=booking_id)

    def create(self, **fields) -> PaymentRow:
        row = PaymentRow(**fields)
        self.session.add(row)
        return row


class CommissionRepository(SqlRepository[CommissionRow]):
    model = CommissionRow
    not_found_code = error_codes.PAYMENT_NOT_FOUND

    def create(self, **fields) -> CommissionRow:
        row = CommissionRow(**fields)
        self.session.add(row)
        return row

    def find_for_booking(self, booking_id: str) -> CommissionRow | None:
        return self.find_by(booking_id=booking_id)


class WalletRepository(SqlRepository[WalletRow]):
    model = WalletRow
    not_found_code = error_codes.WALLET_NOT_FOUND

    def get_or_create(self, driver_id: str, currency: str = "AFN") -> WalletRow:
        row = self.session.scalars(
            self._base().where(
                WalletRow.driver_id == driver_id, WalletRow.currency == currency
            ).with_for_update()
        ).one_or_none()
        if row is None:
            row = WalletRow(id=new_id(), driver_id=driver_id, currency=currency)
            self.session.add(row)
            self.session.flush()
        return row

    def append(
        self,
        *,
        wallet: WalletRow,
        kind: str,
        amount_minor: int,
        booking_id: str | None = None,
        trip_id: str | None = None,
        settlement_id: str | None = None,
        note: str | None = None,
    ) -> WalletTransactionRow:
        """One ledger entry plus the balance it produces.

        ``balance_after_minor`` is stored on every entry so the ledger can be
        audited without replaying it, and so a discrepancy is visible at the row
        where it first appeared.
        """
        wallet.available_minor += amount_minor
        if amount_minor > 0:
            wallet.lifetime_earned_minor += amount_minor
        wallet.version += 1
        self.session.add(wallet)

        entry = WalletTransactionRow(
            id=new_id(),
            wallet_id=wallet.id,
            kind=kind,
            amount_minor=amount_minor,
            currency=wallet.currency,
            balance_after_minor=wallet.available_minor,
            booking_id=booking_id,
            trip_id=trip_id,
            settlement_id=settlement_id,
            note=note,
        )
        self.session.add(entry)
        return entry

    def ledger(self, wallet_id: str, *, limit: int = 50, offset: int = 0):
        stmt = (
            select(WalletTransactionRow)
            .where(
                WalletTransactionRow.wallet_id == wallet_id,
                WalletTransactionRow.deleted_at.is_(None),
            )
            .order_by(WalletTransactionRow.created_at.desc())
            .limit(min(limit, 200))
            .offset(offset)
        )
        return list(self.session.scalars(stmt).all())


class SettlementRepository(SqlRepository[SettlementRow]):
    model = SettlementRow
    not_found_code = error_codes.WALLET_NOT_FOUND

    def create(self, **fields) -> SettlementRow:
        row = SettlementRow(**fields)
        self.session.add(row)
        return row
