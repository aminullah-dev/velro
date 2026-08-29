"""جواز سیر belongs to the vehicle, not the driver

Revision ID: a1c73f9e2b40
Revises: fd2262b18e90

VEHICLE_REGISTRATION was a driver document, so a driver who owns two cars had
one slot for it and the first car's permit stood in for the second. It moves to
a table of its own, hanging off the vehicle.

Existing rows are moved, not recreated: the file_key, the verification and the
expiry date all come across, so nothing has to be photographed or reviewed
again. A driver's VEHICLE_REGISTRATION attaches to their newest vehicle that is
not retired -- the one the document was almost certainly for.

Rollback note: down() moves the rows back onto their vehicle's driver and drops
the table. A driver with two vehicles that each grew their own permit after this
migration would collapse back to one on the way down, which is the defect this
migration exists to fix; the losing row is reported by the query in the note
below rather than silently dropped.

    SELECT driver_id, count(*) FROM vehicles v
      JOIN vehicle_documents d ON d.vehicle_id = v.id
     WHERE d.deleted_at IS NULL AND v.deleted_at IS NULL
     GROUP BY driver_id HAVING count(*) > 1;
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c73f9e2b40"
down_revision: str | None = "fd2262b18e90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MOVED_TYPE = "VEHICLE_REGISTRATION"


def upgrade() -> None:
    op.create_table(
        "vehicle_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "vehicle_id",
            sa.String(36),
            sa.ForeignKey("vehicles.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("document_type_code", sa.String(40), nullable=False),
        sa.Column("file_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="PENDING"),
        sa.Column("expires_on", sa.Date()),
        sa.Column("verified_by", sa.String(36)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("rejection_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(36)),
        sa.Column("updated_by", sa.String(36)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'VERIFIED', 'REJECTED')",
            name="ck_vehicle_documents_status",
        ),
    )
    op.create_index(
        "ix_vehicle_documents_vehicle_id", "vehicle_documents", ["vehicle_id"]
    )
    op.create_index(
        "ix_vehicle_documents_vehicle_id_document_type_code",
        "vehicle_documents",
        ["vehicle_id", "document_type_code"],
    )

    # Move the rows. Everything comes across -- the same file, the same
    # verification, the same expiry -- so no driver has to re-photograph a
    # permit an administrator has already looked at.
    #
    # DISTINCT ON picks each driver's newest vehicle that is not retired. A
    # driver with several cars had one permit standing in for all of them, and
    # the newest live car is the likeliest one it was actually issued for. An
    # operator can move it if that guess is wrong; the alternative -- attaching
    # it to every car -- would silently certify vehicles nobody checked.
    op.execute(
        sa.text(
            """
            WITH target AS (
                SELECT DISTINCT ON (driver_id) driver_id, id AS vehicle_id
                  FROM vehicles
                 WHERE deleted_at IS NULL AND status <> 'RETIRED'
                 ORDER BY driver_id, created_at DESC
            )
            INSERT INTO vehicle_documents (
                id, vehicle_id, document_type_code, file_key, status, expires_on,
                verified_by, verified_at, rejection_reason,
                created_at, updated_at, deleted_at, created_by, updated_by, version
            )
            SELECT d.id, t.vehicle_id, d.document_type_code, d.file_key, d.status,
                   d.expires_on, d.verified_by, d.verified_at, d.rejection_reason,
                   d.created_at, d.updated_at, d.deleted_at, d.created_by,
                   d.updated_by, d.version
              FROM driver_documents d
              JOIN target t ON t.driver_id = d.driver_id
             WHERE d.document_type_code = :moved
            """
        ).bindparams(moved=MOVED_TYPE)
    )

    # Only what was moved is removed. A VEHICLE_REGISTRATION belonging to a
    # driver with no live vehicle has nowhere to go, so it stays where it is
    # rather than being deleted -- it is a photograph of a real permit, and the
    # driver can attach it when they register the car. It no longer counts
    # towards anything, because the setting below stops asking drivers for it.
    op.execute(
        sa.text(
            """
            DELETE FROM driver_documents
             WHERE document_type_code = :moved
               AND id IN (SELECT id FROM vehicle_documents)
            """
        ).bindparams(moved=MOVED_TYPE)
    )

    # The two settings rows. Written as JSON in the same {'v': [...]} envelope
    # the settings service reads.
    op.execute(
        sa.text(
            """
            UPDATE app_settings
               SET value = '{"v": ["LICENSE", "NATIONAL_ID", "SELFIE"]}'::json,
                   version = version + 1
             WHERE key = 'driver.required_documents'
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO app_settings (
                id, key, value, value_type, description_key, is_secret,
                created_at, updated_at, version
            )
            SELECT :id, 'vehicle.required_documents',
                   '{"v": ["VEHICLE_REGISTRATION"]}'::json, 'list',
                   'setting.vehicle_required_documents', false,
                   now(), now(), 1
             WHERE NOT EXISTS (
                SELECT 1 FROM app_settings WHERE key = 'vehicle.required_documents'
             )
            """
        ).bindparams(id="01a05000-0000-7000-8000-000000000001")
    )
    op.execute(
        sa.text(
            """
            INSERT INTO app_settings (
                id, key, value, value_type, description_key, is_secret,
                created_at, updated_at, version
            )
            SELECT :id, 'vehicle.optional_documents', '{"v": []}'::json, 'list',
                   'setting.vehicle_optional_documents', false, now(), now(), 1
             WHERE NOT EXISTS (
                SELECT 1 FROM app_settings WHERE key = 'vehicle.optional_documents'
             )
            """
        ).bindparams(id="01a05000-0000-7000-8000-000000000002")
    )

    # Any car left ACTIVE without a valid permit goes back to PENDING.
    #
    # Found by running this migration against a real database: a driver whose
    # VEHICLE_REGISTRATION was never uploaded had an ACTIVE car, and after the
    # move that car was ACTIVE with no permit at all -- a state the application
    # will no longer produce, because activation now checks the papers. Leaving
    # those rows would mean the database holds a state the code calls
    # impossible, and the first thing anyone would notice is the driver being
    # refused at the roadside with an ACTIVE car on their screen.
    #
    # PENDING is the honest state: the driver sends the جواز سیر and an
    # operator activates the car, which is the flow from here on.
    op.execute(
        sa.text(
            """
            UPDATE vehicles v
               SET status = 'PENDING', version = version + 1
             WHERE v.deleted_at IS NULL
               AND v.status = 'ACTIVE'
               AND EXISTS (
                     SELECT 1 FROM app_settings s
                      WHERE s.key = 'vehicle.required_documents'
                        AND json_array_length(s.value -> 'v') > 0
                   )
               -- "some required code has no valid document" -- i.e. incomplete.
               AND EXISTS (
                     SELECT 1
                       FROM json_array_elements_text(
                              (SELECT value -> 'v' FROM app_settings
                                WHERE key = 'vehicle.required_documents')
                            ) AS required(code)
                      WHERE NOT EXISTS (
                            SELECT 1 FROM vehicle_documents d
                             WHERE d.vehicle_id = v.id
                               AND d.deleted_at IS NULL
                               AND d.document_type_code = required.code
                               AND d.status = 'VERIFIED'
                               AND (d.expires_on IS NULL OR d.expires_on >= current_date)
                          )
                   )
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO driver_documents (
                id, driver_id, document_type_code, file_key, status, expires_on,
                verified_by, verified_at, rejection_reason,
                created_at, updated_at, deleted_at, created_by, updated_by, version
            )
            SELECT d.id, v.driver_id, d.document_type_code, d.file_key, d.status,
                   d.expires_on, d.verified_by, d.verified_at, d.rejection_reason,
                   d.created_at, d.updated_at, d.deleted_at, d.created_by,
                   d.updated_by, d.version
              FROM vehicle_documents d
              JOIN vehicles v ON v.id = d.vehicle_id
             WHERE NOT EXISTS (
                SELECT 1 FROM driver_documents existing WHERE existing.id = d.id
             )
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE app_settings
               SET value =
                   '{"v": ["LICENSE", "NATIONAL_ID", "SELFIE", "VEHICLE_REGISTRATION"]}'::json,
                   version = version + 1
             WHERE key = 'driver.required_documents'
            """
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM app_settings "
            "WHERE key IN ('vehicle.required_documents', 'vehicle.optional_documents')"
        )
    )
    op.drop_index("ix_vehicle_documents_vehicle_id_document_type_code", "vehicle_documents")
    op.drop_index("ix_vehicle_documents_vehicle_id", "vehicle_documents")
    op.drop_table("vehicle_documents")
