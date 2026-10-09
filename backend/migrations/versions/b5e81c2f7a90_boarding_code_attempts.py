"""A limit on boarding-code guesses, and a longer code

The trip's own driver could try boarding codes without limit. Two columns on
trips hold the count of wrong codes since the last lockout and the lockout
itself; VerifyPassenger spends an attempt before comparing, in a transaction
of its own, and refuses every code while the trip is locked.

The code grows from four characters to six for bookings made from now on.
Every driver build takes 3 to 8 characters and every passenger build prints
the string it is given, so nothing in the field breaks; existing bookings
keep the codes they already hold. The setting is a row the seed wrote, so it
is moved here -- but only if it still holds the seeded 4: a value an operator
chose is theirs.

Revision ID: b5e81c2f7a90
Revises: 7e3b1d9c5a24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b5e81c2f7a90"
down_revision = "7e3b1d9c5a24"
branch_labels = None
depends_on = None

_LENGTH_KEY = "booking.verification_code_length"


def upgrade() -> None:
    op.add_column(
        "trips",
        sa.Column("boarding_failures", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "trips",
        sa.Column("boarding_locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE app_settings SET value = CAST(:value AS json), version = version + 1, "
            "updated_at = now() WHERE key = :key AND value->>'v' = '4'"
        ).bindparams(value='{"v": 6}', key=_LENGTH_KEY)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE app_settings SET value = CAST(:value AS json), version = version + 1, "
            "updated_at = now() WHERE key = :key AND value->>'v' = '6'"
        ).bindparams(value='{"v": 4}', key=_LENGTH_KEY)
    )
    op.drop_column("trips", "boarding_locked_until")
    op.drop_column("trips", "boarding_failures")
