"""Somewhere for a handset's dying words to land.

The apps are sideloaded; there is no store console, no Crashlytics, no
third-party anything -- the ethos that keeps the product cheap also keeps it
blind. When the app falls over in a valley two hours from the developer, the
stack trace either reaches this table on the next launch or it never existed.

Unauthenticated on the way in (a crash can precede sign-in), so nothing
personal lives here: an app name, a version, a device model and the trace.

Revision ID: c9e42a71f5d8
Revises: a7c31d5e08b4
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c9e42a71f5d8"
down_revision = "a7c31d5e08b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crash_reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("app", sa.String(20), nullable=False),
        sa.Column("version_code", sa.Integer(), nullable=False),
        sa.Column("version_name", sa.String(40), nullable=False),
        sa.Column("device", sa.String(120), nullable=False),
        sa.Column("sdk", sa.Integer(), nullable=False),
        sa.Column("stack", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_crash_reports_received_at", "crash_reports", ["received_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_crash_reports_received_at", table_name="crash_reports")
    op.drop_table("crash_reports")
