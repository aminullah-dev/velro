"""An email address on a user, for the people who run the service.

Sign-in is a phone number and a code, and stays so: most of Ghorband has no
email address, and the phone is the identity. This column exists for the
staff, whose console code can now travel by email instead of by SMS -- free
where an Afghan carrier charges nearly half a dollar, and reachable from a
laptop in Canada when the Roshan SIM is in a drawer in Parwan.

Nullable, because almost every row will stay empty. Unique where present,
enforced by the database and not by a check, because two staff accounts
sharing an inbox is two keys to one door.

Revision ID: f2727dd1984a
Revises: c9e42a71f5d8
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f2727dd1984a"
down_revision = "c9e42a71f5d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(254), nullable=True))
    op.create_index(
        "uq_users_email",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
        sqlite_where=sa.text("email IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_email", table_name="users")
    op.drop_column("users", "email")
