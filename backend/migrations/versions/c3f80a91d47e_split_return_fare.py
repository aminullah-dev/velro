"""split return fare

Revision ID: c3f80a91d47e
Revises: b7e91c3d5a02
Created: 2026-08-30 23:10:00.000000

Rollback note: drops the two return-leg fare columns. A round trip becomes a
request and an offer carrying only the outbound number, which is what they
carried before this migration -- but the return *time* survives in
`return_for`, so a rolled-back row would show a return with no price for it.
Roll back only alongside b7e91c3d5a02.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c3f80a91d47e'
down_revision: str | None = 'b7e91c3d5a02'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Price the two legs separately.

    The existing money columns keep their meaning for a one-way journey and
    become the *outbound* leg of a round trip; the new ones hold the return.
    Nothing has to be backfilled, because every row that exists today is one
    way -- `return_for` was added one migration ago and nothing has used it
    yet.

    Nullable, and null means "no return leg", not "a return leg costing
    nothing". A zero would be a real price agreed at zero afghani, which is a
    different claim about the world.

    No currency column beside them. A journey is priced in one currency; the
    return leg borrows the currency already on the row, and a second currency
    column would be a place for the two to disagree.
    """
    op.add_column(
        "ride_requests",
        sa.Column("return_fare_minor", sa.Integer(), nullable=True),
    )
    op.add_column(
        "fare_offers",
        sa.Column("return_amount_minor", sa.Integer(), nullable=True),
    )
    # A price is a positive number or absent. Enforced here rather than only in
    # the use case: the constraint outlives whichever code path writes the row.
    op.create_check_constraint(
        "ck_ride_requests_return_fare_positive",
        "ride_requests",
        "return_fare_minor IS NULL OR return_fare_minor > 0",
    )
    op.create_check_constraint(
        "ck_fare_offers_return_amount_positive",
        "fare_offers",
        "return_amount_minor IS NULL OR return_amount_minor > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_fare_offers_return_amount_positive", "fare_offers")
    op.drop_constraint("ck_ride_requests_return_fare_positive", "ride_requests")
    op.drop_column("fare_offers", "return_amount_minor")
    op.drop_column("ride_requests", "return_fare_minor")
