"""route stops partial unique

Revision ID: e405b0b4c024
Revises: 73ba4e3b4c32
Created: 2026-08-29

Rollback note: restores the plain unique constraint. Safe only while no route
has both a live and a soft-deleted stop at the same sequence -- after a
regeneration it will, so a rollback needs the dead rows purged first.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e405b0b4c024"
down_revision: str | None = "73ba4e3b4c32"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Let a soft-deleted stop stop occupying its sequence.

    Regenerating a route rebuilds its stops: the old ones are soft-deleted and
    new ones inserted at the same sequences. The plain constraint counted the
    dead rows, so the insert collided and regeneration failed outright -- which
    is every village import after the first, since imported stations have no
    routes until the generator runs.

    A partial index is the fix rather than hard-deleting the stops, because the
    house rule is soft delete and the exception should be the index, not the
    data.
    """
    op.drop_constraint("uq_route_stops_route_id_sequence", "route_stops", type_="unique")
    op.create_index(
        "uq_route_stops_route_id_sequence",
        "route_stops",
        ["route_id", "sequence"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_route_stops_route_id_sequence", table_name="route_stops")
    op.create_unique_constraint(
        "uq_route_stops_route_id_sequence", "route_stops", ["route_id", "sequence"]
    )
