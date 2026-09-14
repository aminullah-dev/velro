"""Make App Review's number an approved driver with a car in service.

App Review signs in to VELRO Driver with the same number as VELRO Ride
(+12025550142, on OTP_TEST_NUMBERS and GEOFENCE_EXEMPT_PHONES). A reviewer
who lands on "awaiting approval" cannot go online, and that is a rejection
under guideline 2.1 -- and nobody at VELRO can approve a stranger through the
app. So this does, once, what the office would: a driver row, APPROVED; the
papers the settings require, VERIFIED; one car, ACTIVE, with its permit.

The papers carry no pictures: their file keys name nothing in storage, and
the driver screen shows only their status. Asking the reviewer not to replace
them is in the review notes -- an upload sends the driver back to PENDING.

Idempotent, and it only ever touches this one number's rows. Refuses a
number that is not on OTP_TEST_NUMBERS: this is not a way to approve a real
person without looking at their tazkira.

    docker compose exec -T api python - +12025550142 < backend/scripts/make-review-driver.py
    PYTHONPATH=. .venv/bin/python scripts/make-review-driver.py +12025550142   # local
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from domain.driver import normalise_plate
from domain.enums import DocumentStatus, DriverApprovalStatus, DriverAvailability, VehicleStatus
from domain.identity import DRIVER, PhoneNumber
from infrastructure.db.models.supply import (
    DriverDocumentRow,
    DriverRow,
    VehicleDocumentRow,
    VehicleRow,
)
from infrastructure.db.repositories.identity import UserRepository
from infrastructure.services.settings import SqlSettingsProvider
from shared.ids import new_id

PLATE = "TEST-0142"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phone", help="App Review's number, as on OTP_TEST_NUMBERS")
    args = parser.parse_args()

    phone = PhoneNumber.parse(args.phone)
    raw = os.environ.get("VELRO_OTP_TEST_NUMBERS", "")
    listed = {n.strip() for n in raw.split(",") if n.strip()}
    if phone.value not in listed:
        print(f"{phone.value} is not on OTP_TEST_NUMBERS; refusing to approve a real person")
        return 1

    url = os.environ.get(
        "VELRO_DATABASE_URL",
        "postgresql+psycopg://aminullahhashemi@localhost:5432/velro_dev",
    )
    now = datetime.now(UTC)
    with Session(create_engine(url)) as session:
        users = UserRepository(session)
        user = users.find_by_phone(phone.value)
        if user is None:
            user = users.create(id=new_id(), phone=phone.value, locale="en", full_name="App Review")
            session.flush()
            print(f"created account for {phone.value}")
        users.grant_role(user.id, DRIVER)

        driver = session.scalars(select(DriverRow).where(DriverRow.user_id == user.id)).first()
        if driver is None:
            driver = DriverRow(
                id=new_id(), user_id=user.id,
                approval_status=DriverApprovalStatus.PENDING.value,
                availability=DriverAvailability.OFFLINE.value,
            )
            session.add(driver)
            session.flush()
        driver.approval_status = DriverApprovalStatus.APPROVED.value
        driver.approved_at = driver.approved_at or now
        driver.suspended_reason = None

        settings = SqlSettingsProvider(session)
        held = {d.document_type_code for d in session.scalars(
            select(DriverDocumentRow).where(
                DriverDocumentRow.driver_id == driver.id,
                DriverDocumentRow.status == DocumentStatus.VERIFIED.value,
            )
        )}
        for code in settings.get_list("driver.required_documents", []):
            if code not in held:
                session.add(DriverDocumentRow(
                    id=new_id(), driver_id=driver.id, document_type_code=code,
                    file_key=f"review/{driver.id}/{code.lower()}.jpg",
                    status=DocumentStatus.VERIFIED.value, verified_at=now,
                ))

        vehicle = session.scalars(
            select(VehicleRow).where(VehicleRow.driver_id == driver.id)
        ).first()
        if vehicle is None:
            vehicle = VehicleRow(
                id=new_id(), driver_id=driver.id,
                plate_number=PLATE, plate_key=normalise_plate(PLATE),
                vehicle_type_code="SEDAN", seat_capacity=4,
                brand="Toyota", model="Corolla", year=2015, colour="White",
                status=VehicleStatus.ACTIVE.value,
            )
            session.add(vehicle)
            session.flush()
        vehicle.status = VehicleStatus.ACTIVE.value

        held = {d.document_type_code for d in session.scalars(
            select(VehicleDocumentRow).where(
                VehicleDocumentRow.vehicle_id == vehicle.id,
                VehicleDocumentRow.status == DocumentStatus.VERIFIED.value,
            )
        )}
        for code in settings.get_list("vehicle.required_documents", []):
            if code not in held:
                session.add(VehicleDocumentRow(
                    id=new_id(), vehicle_id=vehicle.id, document_type_code=code,
                    file_key=f"review/{vehicle.id}/{code.lower()}.jpg",
                    status=DocumentStatus.VERIFIED.value, verified_at=now,
                ))

        session.commit()
        print(
            f"{phone.value}: driver {driver.id} APPROVED, "
            f"car {vehicle.plate_number} ACTIVE, papers VERIFIED"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
