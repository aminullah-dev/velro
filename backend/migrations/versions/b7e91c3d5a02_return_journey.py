"""return journey

Revision ID: b7e91c3d5a02
Revises: a1c73f9e2b40
Created: 2026-08-30 22:20:00.000000

Rollback note: drops ride_requests.return_for. Nothing else reads it, and a
request with a return simply becomes a one-way request again -- no data that
another table depends on is lost.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b7e91c3d5a02'
down_revision: str | None = 'a1c73f9e2b40'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """When the passenger wants to come back.

    Nullable, because most journeys are one way and a null is the honest
    representation of "they did not say".

    One column rather than a second request row. In Ghorband a car to Charikar
    or Kabul is hired for the journey and the way back together -- one car, one
    driver, one price argued once at the roadside. Modelling the return as a
    separate request would mean a second negotiation, possibly a second driver,
    and a passenger stranded in Kabul if nobody bid on it. The return is a
    property of the ask, not another ask.

    No index: it is never a search key. Requests are found by passenger, by
    status and by expiry, and this is only ever read back with the row.
    """
    op.add_column(
        "ride_requests",
        sa.Column("return_for", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ride_requests", "return_for")
