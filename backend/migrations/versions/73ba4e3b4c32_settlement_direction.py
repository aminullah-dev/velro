"""settlement direction

Revision ID: 73ba4e3b4c32
Revises: 9d747a16cbb1
Created: 2026-08-29 11:59:33.694277

Rollback note: drops settlements.direction. Safe -- every settlement written
before this migration was a payout, which is the default the column takes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '73ba4e3b4c32'
down_revision: str | None = '9d747a16cbb1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Added with a server default so existing rows are valid the moment the
    # column exists, then dropped: the application supplies the value, and a
    # lingering default would let a settlement be written without a direction.
    op.add_column(
        "settlements",
        sa.Column(
            "direction",
            sa.String(length=12),
            nullable=False,
            server_default="PAYOUT",
        ),
    )
    op.alter_column("settlements", "direction", server_default=None)
    op.create_check_constraint(
        "ck_settlements_direction",
        "settlements",
        "direction IN ('PAYOUT', 'COLLECTION')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_settlements_direction", "settlements", type_="check")
    op.drop_column("settlements", "direction")
