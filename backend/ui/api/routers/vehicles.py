"""Vehicle registration and approval, sections 26 and 52."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from application.use_cases.vehicles import (
    DecideVehicle,
    DecideVehicleCommand,
    RegisterVehicle,
    RegisterVehicleCommand,
)
from shared import error_codes
from shared.errors import NotFoundError
from ui.api import deps
from ui.api.errors import ok
from ui.api.schemas.common import Schema

router = APIRouter(tags=["driver"])


class VehicleTypeOut(Schema):
    code: str
    name_key: str
    default_seat_capacity: int


class VehicleOut(Schema):
    id: str
    vehicle_type_code: str
    plate_number: str
    seat_capacity: int
    brand: str | None
    model: str | None
    year: int | None
    colour: str | None
    status: str


class RegisterVehicleIn(Schema):
    vehicle_type_code: str = Field(min_length=1, max_length=24)
    plate_number: str = Field(min_length=1, max_length=32)
    seat_capacity: int | None = Field(default=None, ge=1, le=60)
    brand: str | None = Field(default=None, max_length=60)
    model: str | None = Field(default=None, max_length=60)
    year: int | None = Field(default=None, ge=1950, le=2100)
    colour: str | None = Field(default=None, max_length=40)


class RegisteredVehicleOut(Schema):
    id: str
    plate_number: str
    status: str
    seat_capacity: int
    replaced_id: str | None


class DecideVehicleIn(Schema):
    approve: bool
    reason: str | None = Field(default=None, max_length=500)


def _vehicle_out(row) -> VehicleOut:
    return VehicleOut(
        id=row.id,
        vehicle_type_code=row.vehicle_type_code,
        plate_number=row.plate_number,
        seat_capacity=row.seat_capacity,
        brand=row.brand,
        model=row.model,
        year=row.year,
        colour=row.colour,
        status=row.status,
    )


@router.get("/vehicle-types")
def vehicle_types(
    actor: deps.ActorDep,
    types: Annotated[object, Depends(deps.vehicle_types)],
) -> dict:
    """The list the driver's form is built from.

    Read from the database rather than hard-coded, so adding a type is a row
    (section 105). The name is a key; the app renders it in the driver's own
    language.
    """
    return ok([VehicleTypeOut.model_validate(t).model_dump() for t in types.active()])


@router.get("/driver/vehicle")
def my_vehicle(
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
) -> dict:
    driver = drivers.find_by_user(actor.user_id)
    if driver is None:
        raise NotFoundError(error_codes.DRIVER_NOT_FOUND, user_id=actor.user_id)
    row = vehicles.current_for_driver(driver.id)
    # Null rather than 404: "you have not registered one" is a state the screen
    # renders, not a failure it reports.
    return ok(_vehicle_out(row).model_dump() if row else None)


@router.post("/driver/vehicle")
def register_vehicle(
    body: RegisterVehicleIn,
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
    types: Annotated[object, Depends(deps.vehicle_types)],
    trips: Annotated[object, Depends(deps.trips)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    use_case = RegisterVehicle(
        drivers=drivers, vehicles=vehicles, vehicle_types=types, trips=trips,
        audit=audit, clock=deps.clock(), new_id=deps.new_id,
    )
    result = use_case.execute(
        RegisterVehicleCommand(
            driver_user_id=actor.user_id,
            vehicle_type_code=body.vehicle_type_code,
            plate_number=body.plate_number,
            seat_capacity=body.seat_capacity,
            brand=body.brand,
            model=body.model,
            year=body.year,
            colour=body.colour,
        )
    )
    return ok(
        RegisteredVehicleOut(
            id=result.id,
            plate_number=result.plate_number,
            status=result.status.value,
            seat_capacity=result.seat_capacity,
            replaced_id=result.replaced_id,
        ).model_dump()
    )


@router.post("/admin/vehicles/{vehicle_id}/decide")
def decide_vehicle(
    vehicle_id: str,
    body: DecideVehicleIn,
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
    trips: Annotated[object, Depends(deps.trips)],
    documents: Annotated[object, Depends(deps.vehicle_documents)],
    settings: Annotated[object, Depends(deps.app_settings)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    """Activate a vehicle, or take one out of service."""
    use_case = DecideVehicle(
        vehicles=vehicles, trips=trips, audit=audit, clock=deps.clock(),
        documents=documents, settings=settings,
    )
    status = use_case.execute(
        DecideVehicleCommand(
            vehicle_id=vehicle_id,
            actor_id=actor.user_id,
            actor_role=actor.role,
            approve=body.approve,
            reason=body.reason,
        )
    )
    return ok({"vehicle_id": vehicle_id, "status": status.value})


@router.get("/admin/vehicles/pending")
def pending_vehicles(
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    session: deps.SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict:
    """Vehicles waiting to be activated, with the driver they belong to."""
    from sqlalchemy import select

    from infrastructure.db.models.identity import UserRow
    from infrastructure.db.models.supply import DriverRow, VehicleRow

    stmt = (
        select(VehicleRow, UserRow.full_name, UserRow.phone, DriverRow.approval_status)
        .join(DriverRow, DriverRow.id == VehicleRow.driver_id)
        .join(UserRow, UserRow.id == DriverRow.user_id)
        .where(
            VehicleRow.deleted_at.is_(None),
            VehicleRow.status == "PENDING",
        )
        .order_by(VehicleRow.created_at)
        .limit(limit)
    )
    return ok(
        [
            {
                **_vehicle_out(vehicle).model_dump(),
                "driver_id": vehicle.driver_id,
                "driver_name": name,
                "driver_phone": phone,
                "driver_approval_status": approval,
            }
            for vehicle, name, phone, approval in session.execute(stmt).all()
        ]
    )
