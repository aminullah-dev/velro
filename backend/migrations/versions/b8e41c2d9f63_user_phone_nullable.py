"""A deleted account has no phone number.

The number is the identity: it is how somebody signs in, and it is what the
unique constraint guards. An account its owner deleted must let go of it --
otherwise the same SIM can never open a fresh account, and the old number sits
in the table as personal data nobody has a reason to hold. A placeholder
string would have kept the column NOT NULL, and would then be printed as a
"phone number" on every old receipt that shows the other side of a trip. NULL
is what the code already renders as "no number", and the unique constraint
lets any number of NULLs coexist.

Revision ID: b8e41c2d9f63
Revises: a3d9e17c5b02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b8e41c2d9f63"
down_revision = "a3d9e17c5b02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("phone", existing_type=sa.String(20), nullable=True)


def downgrade() -> None:
    # Only reversible while no account has been deleted: a deleted account's
    # number is gone, and there is nothing to put back.
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.alter_column("phone", existing_type=sa.String(20), nullable=False)
