"""negotiated fares

Revision ID: fd2262b18e90
Revises: e405b0b4c024

Rollback note: drops fare_offers and the negotiation columns. The agreed fare
of every completed trip is already copied onto its booking, so a rollback loses
the negotiation record but no money history.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "fd2262b18e90"
down_revision: str | None = "e405b0b4c024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The passenger's asking price replaces the platform quote. quoted_fare_*
    # is kept rather than dropped: any request written before this had a system
    # quote, and deleting it would erase what those passengers were actually
    # told.
    op.add_column(
        "ride_requests",
        sa.Column("offered_fare_minor", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "ride_requests",
        sa.Column(
            "offered_fare_currency", sa.String(length=3), nullable=False,
            server_default="AFN",
        ),
    )
    op.add_column("ride_requests", sa.Column("agreed_fare_minor", sa.Integer()))
    op.add_column("ride_requests", sa.Column("accepted_offer_id", sa.String(length=36)))
    op.add_column("ride_requests", sa.Column("note", sa.Text()))
    # Carry the old quote across as the asking price, so an in-flight request
    # is not left asking for nothing.
    op.execute(
        "UPDATE ride_requests SET offered_fare_minor = COALESCE(quoted_fare_minor, 0)"
    )
    op.alter_column("ride_requests", "offered_fare_minor", server_default=None)
    op.alter_column("ride_requests", "offered_fare_currency", server_default=None)
    op.create_check_constraint(
        "ck_ride_requests_offer_positive", "ride_requests", "offered_fare_minor > 0"
    )
    op.create_index(
        "ix_ride_requests_origin_status", "ride_requests",
        ["origin_station_id", "status"],
    )
    op.create_index(
        "ix_ride_requests_accepted_offer_id", "ride_requests", ["accepted_offer_id"]
    )

    op.create_table(
        "fare_offers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("ride_request_id", sa.String(length=36), nullable=False),
        sa.Column("driver_id", sa.String(length=36), nullable=False),
        sa.Column("vehicle_id", sa.String(length=36)),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("amount_currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(length=36)),
        sa.Column("updated_by", sa.String(length=36)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_fare_offers"),
        sa.ForeignKeyConstraint(
            ["ride_request_id"], ["ride_requests.id"],
            name="fk_fare_offers_ride_request_id", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["driver_id"], ["drivers.id"],
            name="fk_fare_offers_driver_id", ondelete="RESTRICT",
        ),
        sa.CheckConstraint("amount_minor > 0", name="ck_fare_offers_amount_positive"),
        sa.CheckConstraint(
            "status IN ('OFFERED','ACCEPTED','DECLINED','WITHDRAWN','EXPIRED')",
            name="ck_fare_offers_status",
        ),
    )
    op.create_index("ix_fare_offers_ride_request_id", "fare_offers", ["ride_request_id"])
    op.create_index("ix_fare_offers_driver_id", "fare_offers", ["driver_id"])
    op.create_index("ix_fare_offers_deleted_at", "fare_offers", ["deleted_at"])
    # Partial: one *live* offer per driver per request. A withdrawn one must not
    # stop them offering again, which is the whole point of withdrawing.
    op.create_index(
        "uq_fare_offers_request_driver_open",
        "fare_offers",
        ["ride_request_id", "driver_id"],
        unique=True,
        postgresql_where=sa.text("status = 'OFFERED'"),
    )


def downgrade() -> None:
    op.drop_table("fare_offers")
    op.drop_index("ix_ride_requests_accepted_offer_id", table_name="ride_requests")
    op.drop_index("ix_ride_requests_origin_status", table_name="ride_requests")
    op.drop_constraint("ck_ride_requests_offer_positive", "ride_requests", type_="check")
    for column in ("note", "accepted_offer_id", "agreed_fare_minor",
                   "offered_fare_currency", "offered_fare_minor"):
        op.drop_column("ride_requests", column)
