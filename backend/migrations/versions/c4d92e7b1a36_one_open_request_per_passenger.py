"""One open ride request per passenger, as a partial unique index

ADR 0004 says a passenger has one open request at a time. RequestRide looked
for one and then inserted, and two asks in the same instant both found none.
The index makes the rule a constraint; RequestRide turns its refusal into
RIDE_REQUEST_ALREADY_OPEN.

Existing rows first, because the index cannot be built over a passenger who
already has two:

1. Requests still marked OPEN after their deadline are marked EXPIRED. Every
   reader already treats them as closed -- RideRequestRepository's
   expire_stale and expire_stale_for_passenger make exactly this write the
   next time anyone looks -- so this changes what the rows say, not what
   they mean. Nothing is deleted.
2. If any passenger still has two or more OPEN requests whose deadline has
   not passed, the migration stops with an error naming how many, and
   changes nothing (the transaction is rolled back). Which of two live
   requests to close is a decision about somebody's journey, and it is not
   one a migration should make. The query below finds them; close the extra
   ones by hand (or wait for their deadline) and run the upgrade again.

       SELECT passenger_id, count(*) FROM ride_requests
       WHERE status = 'OPEN' AND deleted_at IS NULL AND expires_at > now()
       GROUP BY passenger_id HAVING count(*) > 1;

Revision ID: c4d92e7b1a36
Revises: b5e81c2f7a90
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c4d92e7b1a36"
down_revision = "b5e81c2f7a90"
branch_labels = None
depends_on = None

_INDEX = "uq_ride_requests_passenger_open"
_OPEN = "status = 'OPEN' AND deleted_at IS NULL"


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE ride_requests SET status = 'EXPIRED', version = version + 1, "
            "updated_at = now() "
            f"WHERE {_OPEN} AND expires_at <= now()"
        )
    )
    passengers = bind.execute(
        sa.text(
            "SELECT count(*) FROM (SELECT passenger_id FROM ride_requests "
            f"WHERE {_OPEN} GROUP BY passenger_id HAVING count(*) > 1) AS twice"
        )
    ).scalar_one()
    if passengers:
        raise RuntimeError(
            f"{passengers} passenger(s) hold more than one live OPEN ride request, so "
            f"{_INDEX} cannot be built. Nothing was changed. Close the extra requests "
            "(see this migration's docstring for the query) and run the upgrade again."
        )
    op.create_index(
        _INDEX,
        "ride_requests",
        ["passenger_id"],
        unique=True,
        postgresql_where=sa.text(_OPEN),
        sqlite_where=sa.text(_OPEN),
    )


def downgrade() -> None:
    # The requests expired on the way up stay expired: their deadline had
    # passed, and every reader treated them as closed before and after.
    op.drop_index(_INDEX, table_name="ride_requests")
