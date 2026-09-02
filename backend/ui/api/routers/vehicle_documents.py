"""The car's own papers: جواز سیر, per vehicle.

A driver may own more than one car, so these hang off a vehicle id rather than
off the driver. Every read and write checks that the vehicle belongs to the
driver asking -- a permit is what an administrator activates a car on, and
attaching one to somebody else's car would certify a vehicle nobody inspected.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from pydantic import Field

from application.use_cases.vehicle_documents import (
    ReviewVehicleDocument,
    ReviewVehicleDocumentCommand,
    UploadVehicleDocument,
    UploadVehicleDocumentCommand,
    to_vehicle,
)
from shared import error_codes
from shared.errors import NotFoundError
from ui.api import deps
from ui.api.errors import ok
from ui.api.schemas.common import Schema

router = APIRouter(tags=["driver"])


class VehicleDocumentOut(Schema):
    id: str
    vehicle_id: str
    document_type_code: str
    status: str
    expires_on: date | None
    rejection_reason: str | None
    uploaded_at: datetime
    reviewed_at: datetime | None
    is_current: bool


class VehicleChecklistOut(Schema):
    """What this car still needs, and where each paper stands."""

    vehicle_id: str
    plate_number: str
    required: list[str]
    missing: list[str]
    documents: list[VehicleDocumentOut]
    vehicle_status: str
    can_carry: bool


class UploadedOut(Schema):
    id: str
    vehicle_id: str
    document_type_code: str
    status: str
    supersedes_id: str | None


class ReviewIn(Schema):
    verified: bool
    rejection_reason: str | None = Field(default=None, max_length=500)
    expires_on: date | None = None


class ReviewOut(Schema):
    document_id: str
    vehicle_id: str
    status: str
    vehicle_now_complete: bool
    missing_documents: list[str]


def _document_out(row, current_ids: set[str]) -> VehicleDocumentOut:
    return VehicleDocumentOut(
        id=row.id,
        vehicle_id=row.vehicle_id,
        document_type_code=row.document_type_code,
        status=row.status,
        expires_on=row.expires_on,
        rejection_reason=row.rejection_reason,
        uploaded_at=row.created_at,
        reviewed_at=row.verified_at,
        is_current=row.id in current_ids,
    )


def _checklist(vehicle_row, documents, settings) -> VehicleChecklistOut:
    rows = documents.for_vehicle(vehicle_row.id)
    required = settings.get_list("vehicle.required_documents", [])

    current_ids = set()
    seen: set[str] = set()
    for row in rows:                      # already newest first
        if row.document_type_code not in seen:
            seen.add(row.document_type_code)
            current_ids.add(row.id)

    vehicle = to_vehicle(vehicle_row, rows)
    missing = vehicle.missing_documents(
        frozenset(required), on=deps.clock().now().date()
    )

    return VehicleChecklistOut(
        vehicle_id=vehicle_row.id,
        plate_number=vehicle_row.plate_number,
        required=required,
        missing=sorted(missing),
        documents=[_document_out(row, current_ids) for row in rows],
        vehicle_status=vehicle_row.status,
        can_carry=vehicle.is_usable and not missing,
    )


def _own_vehicle(vehicle_id: str, actor, drivers, vehicles):
    """The driver's own car, or a 404.

    Deliberately the same answer whether the car belongs to someone else or
    does not exist, so the endpoint cannot be used to enumerate vehicle ids.
    """
    driver = drivers.find_by_user(actor.user_id)
    if driver is None:
        raise NotFoundError(error_codes.DRIVER_NOT_FOUND, user_id=actor.user_id)
    row = vehicles.get(vehicle_id)
    if row.driver_id != driver.id:
        raise NotFoundError(error_codes.VEHICLE_NOT_FOUND, vehicle_id=vehicle_id)
    return row


def _file_response(row) -> Response:
    # Storage answers with a StoredFileContent, as documents.py reads it. This
    # unpacked it as a pair and raised on every request -- unnoticed because
    # no app ever asked for a vehicle document's bytes until the driver's
    # screen started showing his جواز سیر photo.
    stored = deps.file_storage().get(row.file_key)
    return Response(
        content=stored.content,
        media_type=stored.content_type,
        headers={
            # Never cached by a proxy: these are scans of legal documents.
            "cache-control": "private, no-store",
            "content-disposition": "inline",
        },
    )


# -- the driver's side ---------------------------------------------------

@router.get("/driver/vehicles/{vehicle_id}/documents")
def my_vehicle_documents(
    vehicle_id: str,
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
    documents: Annotated[object, Depends(deps.vehicle_documents)],
    settings: Annotated[object, Depends(deps.app_settings)],
) -> dict:
    row = _own_vehicle(vehicle_id, actor, drivers, vehicles)
    return ok(_checklist(row, documents, settings).model_dump())


@router.post("/driver/vehicles/{vehicle_id}/documents")
async def upload_vehicle_document(
    vehicle_id: str,
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
    documents: Annotated[object, Depends(deps.vehicle_documents)],
    settings: Annotated[object, Depends(deps.app_settings)],
    audit: Annotated[object, Depends(deps.audit)],
    file: Annotated[UploadFile, File()],
    document_type_code: Annotated[str, Form()],
    expires_on: Annotated[date | None, Form()] = None,
) -> dict:
    use_case = UploadVehicleDocument(
        drivers=drivers, vehicles=vehicles, documents=documents,
        storage=deps.file_storage(), settings=settings, audit=audit,
        clock=deps.clock(), new_id=deps.new_id,
    )
    result = use_case.execute(
        UploadVehicleDocumentCommand(
            vehicle_id=vehicle_id,
            driver_user_id=actor.user_id,
            document_type_code=document_type_code.strip().upper(),
            content=await file.read(),
            expires_on=expires_on,
        )
    )
    payload = asdict(result)
    payload["status"] = result.status.value
    payload.pop("uploaded_at", None)
    return ok(UploadedOut(**payload).model_dump())


@router.get("/driver/vehicle-documents/{document_id}/file")
def my_vehicle_document_file(
    document_id: str,
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
    documents: Annotated[object, Depends(deps.vehicle_documents)],
) -> Response:
    """A driver may read only the papers of their own cars."""
    row = documents.get(document_id)
    _own_vehicle(row.vehicle_id, actor, drivers, vehicles)
    return _file_response(row)


# -- the reviewer's side -------------------------------------------------

@router.get("/admin/vehicles/{vehicle_id}/documents")
def vehicle_documents_for_review(
    vehicle_id: str,
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
    documents: Annotated[object, Depends(deps.vehicle_documents)],
    settings: Annotated[object, Depends(deps.app_settings)],
) -> dict:
    return ok(_checklist(vehicles.get(vehicle_id), documents, settings).model_dump())


@router.get("/admin/vehicle-documents/{document_id}/file")
def vehicle_document_file(
    document_id: str,
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    documents: Annotated[object, Depends(deps.vehicle_documents)],
) -> Response:
    """Staff may read any vehicle document, through this check and no other way."""
    return _file_response(documents.get(document_id))


@router.post("/admin/vehicle-documents/{document_id}/review")
def review_vehicle_document(
    document_id: str,
    body: ReviewIn,
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    vehicles: Annotated[object, Depends(deps.vehicles)],
    documents: Annotated[object, Depends(deps.vehicle_documents)],
    settings: Annotated[object, Depends(deps.app_settings)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    use_case = ReviewVehicleDocument(
        vehicles=vehicles, documents=documents, settings=settings,
        audit=audit, clock=deps.clock(),
    )
    result = use_case.execute(
        ReviewVehicleDocumentCommand(
            document_id=document_id,
            actor_id=actor.user_id,
            actor_role=actor.role,
            verified=body.verified,
            expires_on=body.expires_on,
            rejection_reason=body.rejection_reason,
        )
    )
    payload = asdict(result)
    payload["status"] = result.status.value
    return ok(ReviewOut(**payload).model_dump())
