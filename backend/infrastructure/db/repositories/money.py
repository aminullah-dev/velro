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
from domain.enums import SettlementStatus, WalletEntryKind
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

    def hold_for_settlement(
        self, *, wallet: WalletRow, amount_minor: int, settlement_id: str, reference: str
    ) -> WalletTransactionRow:
        """Move money from available to pending and write the entry.

        Deliberately not ``append``: that helper treats a negative amount as a
        loss and would leave the money in neither bucket. A payout request does
        not reduce what the driver is owed -- it only stops them asking for the
        same money twice while the office works on it.
        """
        wallet.available_minor -= amount_minor
        wallet.pending_minor += amount_minor
        wallet.version += 1
        self.session.add(wallet)

        entry = WalletTransactionRow(
            id=new_id(),
            wallet_id=wallet.id,
            kind=WalletEntryKind.SETTLEMENT.value,
            amount_minor=-amount_minor,
            currency=wallet.currency,
            balance_after_minor=wallet.available_minor,
            settlement_id=settlement_id,
            note=reference,
        )
        self.session.add(entry)
        return entry

    def release_hold(
        self, *, wallet: WalletRow, amount_minor: int, settlement_id: str, reference: str
    ) -> WalletTransactionRow:
        """A rejected payout. The money was never spent, so it comes back."""
        wallet.pending_minor -= amount_minor
        wallet.available_minor += amount_minor
        wallet.version += 1
        self.session.add(wallet)

        entry = WalletTransactionRow(
            id=new_id(),
            wallet_id=wallet.id,
            kind=WalletEntryKind.SETTLEMENT.value,
            amount_minor=amount_minor,
            currency=wallet.currency,
            balance_after_minor=wallet.available_minor,
            settlement_id=settlement_id,
            note=reference,
        )
        self.session.add(entry)
        return entry

    def settle_hold(self, *, wallet: WalletRow, amount_minor: int) -> None:
        """Paid. The pending bucket drains into the lifetime total.

        No ledger entry: the entry was written when the hold was placed, and the
        driver's available balance does not move now. Writing a second entry
        here would make the ledger sum to less than the driver is owed.
        """
        wallet.pending_minor -= amount_minor
        wallet.lifetime_paid_minor += amount_minor
        wallet.version += 1
        self.session.add(wallet)

    def ledger(self, wallet_id: str, *, limit: int = 50, offset: int = 0):
        stmt = (
            select(WalletTransactionRow)
            .where(
                WalletTransactionRow.wallet_id == wallet_id,
                WalletTransactionRow.deleted_at.is_(None),
            )
            # Newest first, then by id: two entries from the same commit share a
            # timestamp, and without the tiebreak the page boundary can repeat
            # or skip one. Ids are UUIDv7, so this is chronological too.
            .order_by(
                WalletTransactionRow.created_at.desc(), WalletTransactionRow.id.desc()
            )
            .limit(min(limit, 200))
            .offset(offset)
        )
        return list(self.session.scalars(stmt).all())


class SettlementRepository(SqlRepository[SettlementRow]):
    model = SettlementRow
    not_found_code = error_codes.SETTLEMENT_NOT_FOUND

    def create(self, **fields) -> SettlementRow:
        row = SettlementRow(**fields)
        self.session.add(row)
        self.session.flush()
        return row

    def find_open_for_driver(self, driver_id: str) -> SettlementRow | None:
        """The one a driver already has in flight, if any.

        Locked, because two taps on a slow connection are two requests, and
        without this both would read "nothing open" and hold the money twice.
        """
        return self.session.scalars(
            self._base()
            .where(
                SettlementRow.driver_id == driver_id,
                SettlementRow.status.in_(
                    [SettlementStatus.PENDING.value, SettlementStatus.PROCESSING.value]
                ),
            )
            .order_by(SettlementRow.created_at.desc())
            .with_for_update()
        ).first()

    def for_driver(self, driver_id: str, *, limit: int = 20) -> list[SettlementRow]:
        return list(
            self.session.scalars(
                self._base()
                .where(SettlementRow.driver_id == driver_id)
                .order_by(SettlementRow.created_at.desc(), SettlementRow.id.desc())
                .limit(min(limit, 100))
            ).all()
        )

    def open_queue(self, *, limit: int = 100) -> list[SettlementRow]:
        """What the office has to act on, oldest first -- a payout queue is the
        one list where waiting longest should mean being served first."""
        return list(
            self.session.scalars(
                self._base()
                .where(
                    SettlementRow.status.in_(
                        [
                            SettlementStatus.PENDING.value,
                            SettlementStatus.PROCESSING.value,
                        ]
                    )
                )
                .order_by(SettlementRow.created_at.asc())
                .limit(min(limit, 200))
            ).all()
        )
