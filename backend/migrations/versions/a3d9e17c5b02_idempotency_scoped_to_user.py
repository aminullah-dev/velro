"""An idempotency key belongs to the user who sent it.

The table always had a user_id column; nothing wrote it and nothing read it,
and the unique constraint was on the key and the endpoint alone. So a stored
response -- an accepted offer's boarding code among them -- was reachable by
anyone who could name the key, and a key built from an offer id is a key the
driver on the other side of that offer can name.

The constraint now includes the user, and the lookup always does. Rows written
before this (user_id null) match nobody and expire within a day; there is
nothing to migrate.

Revision ID: a3d9e17c5b02
Revises: f2727dd1984a
"""

from __future__ import annotations

from alembic import op

revision = "a3d9e17c5b02"
down_revision = "f2727dd1984a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("idempotency_keys", schema=None) as batch_op:
        batch_op.drop_constraint("uq_idempotency_keys_key_endpoint", type_="unique")
        batch_op.create_unique_constraint(
            "uq_idempotency_keys_user_key_endpoint", ["user_id", "key", "endpoint"]
        )


def downgrade() -> None:
    with op.batch_alter_table("idempotency_keys", schema=None) as batch_op:
        batch_op.drop_constraint("uq_idempotency_keys_user_key_endpoint", type_="unique")
        batch_op.create_unique_constraint(
            "uq_idempotency_keys_key_endpoint", ["key", "endpoint"]
        )
