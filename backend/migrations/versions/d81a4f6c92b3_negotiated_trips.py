"""negotiated trips carry no route, and remember the way back

Revision ID: d81a4f6c92b3
Revises: c3f80a91d47e
Created: 2026-08-30 23:55:00.000000

Rollback note: re-tightening trips.route_id to NOT NULL will fail if any
negotiated trip has been created without a route by then -- which is the whole
point of relaxing it. Delete or backfill those rows first. Dropping
trips.return_for loses the return leg of any round trip already agreed; the
ride_request it came from still has it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd81a4f6c92b3'
down_revision: str | None = 'c3f80a91d47e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Two things the negotiated path needs and the scheduled path never did.

    route_id becomes nullable. RouteRepository.find_for has always said in its
    own docstring that "a negotiated ride does not need one -- two people
    agreed to make the journey whether or not VELRO has modelled it -- so this
    returns None ... and the trip simply carries no route", and AcceptOffer has
    always written `route_id=route.id if route else None` on that basis. The
    column said otherwise, so the two disagreed and the database won: an
    IntegrityError, a 500, and a passenger tapping "take this car" on a journey
    VELRO has not modelled getting a server error she can repeat for ever.
    On production today, 20 of the 90 station-to-destination pairs have no
    active route -- better than a fifth of every journey the valley can ask
    for.

    A scheduled trip still gets its route from its schedule; nothing about that
    path changes.

    return_for is the trip's copy of the return leg. Without it the return
    survived the whole negotiation, was priced, agreed and charged, and then
    ceased to exist the moment the trip was created: the driver's assignment
    showed one leg, the passenger's booking showed one departure, and the only
    row that still knew was the closed ride_request nobody reads again.
    """
    op.alter_column(
        "trips",
        "route_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )
    op.add_column(
        "trips",
        sa.Column("return_for", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trips", "return_for")
    op.alter_column(
        "trips",
        "route_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
