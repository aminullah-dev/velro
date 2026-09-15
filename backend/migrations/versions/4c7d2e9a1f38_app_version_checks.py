"""How many launches each app version had on each day, and nothing else.

The Android apps ask GET /app/version on launch. Until now nobody could say
which of the published builds were still running out there, so "can the old
one stop being served" was a guess. Each question now adds one to a counter
keyed by (day, app, platform, version_code).

Anonymous by construction: no user, no device, no address -- the endpoint
is unauthenticated and this table counts launches; it does not follow
people. A row per version per day, so a year of it is a few thousand rows.

The unique constraint is also the index the dashboard's seven-day read uses
(day leads), and the one the upsert's ON CONFLICT names.

Revision ID: 4c7d2e9a1f38
Revises: b8e41c2d9f63
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "4c7d2e9a1f38"
down_revision = "b8e41c2d9f63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_version_checks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("app", sa.String(16), nullable=False),
        sa.Column("platform", sa.String(12), nullable=False),
        sa.Column("version_code", sa.Integer(), nullable=False),
        sa.Column("version_name", sa.String(32), nullable=False),
        sa.Column("checks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(36)),
        sa.Column("updated_by", sa.String(36)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint(
            "day", "app", "platform", "version_code",
            name="uq_app_version_checks_day_app_platform_version_code",
        ),
    )
    op.create_index(
        "ix_app_version_checks_deleted_at", "app_version_checks", ["deleted_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_app_version_checks_deleted_at", table_name="app_version_checks")
    op.drop_table("app_version_checks")
