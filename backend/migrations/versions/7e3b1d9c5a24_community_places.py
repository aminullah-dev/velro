"""Place names passengers give to where they are standing

A passenger who asks from "my current location" is told the nearest station
and asked what the place is called. The answer is kept in `places` -- once,
not once per report -- so the next passenger there is offered it and the
driver's board can say which village a request came from.

Anonymous by construction (ADR 0015): no user column, and created_by is never
written. The table says "people call this spot X"; it never says who stood
there.

ride_requests.origin_place_id is nullable and only set when the request was
made from the current location. Every existing row stays null.

Revision ID: 7e3b1d9c5a24
Revises: 4c7d2e9a1f38
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "7e3b1d9c5a24"
down_revision = "4c7d2e9a1f38"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "places",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("name_key", sa.String(80), nullable=False),
        sa.Column(
            "district_id",
            sa.String(36),
            sa.ForeignKey("districts.id", ondelete="RESTRICT", name="fk_places_district_id"),
            nullable=False,
        ),
        sa.Column(
            "village_id",
            sa.String(36),
            sa.ForeignKey("villages.id", ondelete="RESTRICT", name="fk_places_village_id"),
        ),
        sa.Column(
            "nearest_station_id",
            sa.String(36),
            sa.ForeignKey("stations.id", ondelete="RESTRICT", name="fk_places_nearest_station_id"),
        ),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="PENDING"),
        sa.Column("report_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(36)),
        sa.Column("updated_by", sa.String(36)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        # op.f: these are the final names. Without it the naming convention
        # prefixes them a second time and the schema drifts from the models.
        sa.CheckConstraint(
            "report_count > 0", name=op.f("ck_places_places_report_count_positive")
        ),
        sa.CheckConstraint(
            "status IN ('APPROVED', 'PENDING', 'REJECTED')",
            name=op.f("ck_places_places_status"),
        ),
    )
    op.create_index("ix_places_deleted_at", "places", ["deleted_at"])
    op.create_index("ix_places_district_id", "places", ["district_id"])
    op.create_index("ix_places_village_id", "places", ["village_id"])
    op.create_index("ix_places_nearest_station_id", "places", ["nearest_station_id"])
    op.create_index("ix_places_district_id_name_key", "places", ["district_id", "name_key"])
    op.create_index("ix_places_latitude_longitude", "places", ["latitude", "longitude"])

    with op.batch_alter_table("ride_requests") as batch_op:
        batch_op.add_column(sa.Column("origin_place_id", sa.String(36), nullable=True))
        batch_op.create_foreign_key(
            "fk_ride_requests_origin_place_id",
            "places",
            ["origin_place_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index("ix_ride_requests_origin_place_id", ["origin_place_id"])


def downgrade() -> None:
    with op.batch_alter_table("ride_requests") as batch_op:
        batch_op.drop_index("ix_ride_requests_origin_place_id")
        batch_op.drop_constraint("fk_ride_requests_origin_place_id", type_="foreignkey")
        batch_op.drop_column("origin_place_id")
    op.drop_index("ix_places_latitude_longitude", table_name="places")
    op.drop_index("ix_places_district_id_name_key", table_name="places")
    op.drop_index("ix_places_nearest_station_id", table_name="places")
    op.drop_index("ix_places_village_id", table_name="places")
    op.drop_index("ix_places_district_id", table_name="places")
    op.drop_index("ix_places_deleted_at", table_name="places")
    op.drop_table("places")
