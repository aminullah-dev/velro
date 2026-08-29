"""vehicle plate key

Revision ID: 9d747a16cbb1
Revises: 5f76dd65710a
Created: 2026-08-29 08:19:49.492389

Rollback note: vehicle plate key
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '9d747a16cbb1'
down_revision: str | None = '5f76dd65710a'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the normalised plate key, backfilled, then enforce uniqueness on it.

    Three steps rather than one: the column cannot be added as NOT NULL to a
    table that already has rows, and the unique constraint cannot be trusted
    until the backfill has run.

    If two existing vehicles normalise to the same key the constraint will
    refuse to build. That is the point -- it means the data already contains one
    vehicle recorded twice, and the migration should stop rather than quietly
    pick a winner.
    """
    op.add_column("vehicles", sa.Column("plate_key", sa.String(length=32), nullable=True))

    # Same rule as domain.driver.normalise_plate: upper case, alphanumeric only.
    # Expressed in SQL so the backfill does not depend on loading the app.
    op.execute(
        """
        UPDATE vehicles
        SET plate_key = regexp_replace(
            upper(
                translate(plate_number, '۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
            ),
            '[^A-Z0-9]', '', 'g'
        )
        """
    )

    op.alter_column("vehicles", "plate_key", nullable=False)
    op.drop_constraint("uq_vehicles_plate_number", "vehicles", type_="unique")
    op.create_unique_constraint("uq_vehicles_plate_key", "vehicles", ["plate_key"])


def downgrade() -> None:
    """Reversible: the raw plate is still there, so nothing is lost."""
    op.drop_constraint("uq_vehicles_plate_key", "vehicles", type_="unique")
    op.create_unique_constraint("uq_vehicles_plate_number", "vehicles", ["plate_number"])
    op.drop_column("vehicles", "plate_key")
