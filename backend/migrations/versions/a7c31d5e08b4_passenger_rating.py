"""A passenger's standing, kept the way a driver's already is.

The ratings table has held both directions since it was written -- rater_role
says which -- and RateTrip already refuses anyone who was not aboard. What was
missing is somewhere for a passenger's running average to live, so the score a
driver gave was recorded and then never added up.

Sum and count rather than a stored average, mirroring drivers exactly: an
average recomputed from a float drifts, and a sum can be corrected if a rating
is ever removed.

Revision ID: a7c31d5e08b4
Revises: d81a4f6c92b3
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a7c31d5e08b4"
down_revision = "d81a4f6c92b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("rating_sum", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "users",
        sa.Column("rating_count", sa.Integer(), nullable=False, server_default="0"),
    )
    # The same two guards the drivers table carries. They are what stops a
    # rounding bug or a bad write from producing an average above five, which
    # nobody would notice until a passenger saw it.
    op.create_check_constraint(
        "ck_users_rating_count_non_negative", "users", "rating_count >= 0"
    )
    op.create_check_constraint(
        "ck_users_rating_sum_within_bounds",
        "users",
        "rating_sum >= 0 AND rating_sum <= rating_count * 5",
    )


def downgrade() -> None:
    op.drop_constraint("ck_users_rating_sum_within_bounds", "users", type_="check")
    op.drop_constraint("ck_users_rating_count_non_negative", "users", type_="check")
    op.drop_column("users", "rating_count")
    op.drop_column("users", "rating_sum")
