"""Driver documents: the driver's side and the reviewer's side.

Files are never served from a public path. Both download routes go through an
authorisation check first -- a driver may see only their own documents, and
staff may see any -- because these are photographs of national identity cards.

Nothing here logs a file key or a file's contents.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from pydantic import Field

from application.use_cases.driver_documents import (
    RegisterDriver,
    RegisterDriverCommand,
    ReviewDocumentCommand,
    ReviewDriverDocument,
    UploadDocumentCommand,
    UploadDriverDocument,
)
from domain.enums import DocumentStatus
from shared import error_codes
from shared.errors import NotFoundError
from ui.api import deps
from ui.api.errors import ok
from ui.api.schemas.common import Schema

router = APIRouter(tags=["driver"])


class DocumentOut(Schema):
    id: str
    document_type_code: str
    status: str
    expires_on: date | None
    rejection_reason: str | None
    uploaded_at: datetime
    reviewed_at: datetime | None
    is_current: bool


class DocumentChecklistOut(Schema):
    """What the driver still has to send, and where each item stands."""

    required: list[str]
    missing: list[str]
    documents: list[DocumentOut]
    approval_status: str
    can_work: bool


class UploadedOut(Schema):
    id: str
    document_type_code: str
    status: str
    supersedes_id: str | None


class ReviewIn(Schema):
    verified: bool
    rejection_reason: str | None = Field(default=None, max_length=500)
    expires_on: date | None = None


class ReviewOut(Schema):
    document_id: str
    driver_id: str
    status: str
    driver_now_complete: bool
    missing_documents: list[str]


class RegisterDriverIn(Schema):
    home_district_id: str | None = None


def _document_out(row, current_ids: set[str]) -> DocumentOut:
    return DocumentOut(
        id=row.id,
        document_type_code=row.document_type_code,
        status=row.status,
        expires_on=row.expires_on,
        rejection_reason=row.rejection_reason,
        uploaded_at=row.created_at,
        reviewed_at=row.verified_at,
        is_current=row.id in current_ids,
    )


def _checklist(driver_row, documents, settings) -> DocumentChecklistOut:
    from application.use_cases.driver_documents import _to_driver

    rows = documents.for_driver(driver_row.id)
    required = settings.get_list("driver.required_documents", [])

    current_ids = set()
    seen: set[str] = set()
    for row in rows:                      # already newest first
        if row.document_type_code not in seen:
            seen.add(row.document_type_code)
            current_ids.add(row.id)

    driver = _to_driver(driver_row, rows)
    missing = driver.missing_documents(frozenset(required), on=deps.clock().now().date())

    return DocumentChecklistOut(
        required=required,
        missing=sorted(missing),
        documents=[_document_out(row, current_ids) for row in rows],
        approval_status=driver_row.approval_status,
        can_work=driver.is_approved and not missing,
    )


# -- the driver's side ---------------------------------------------------

@router.post("/driver/register")
def register_as_driver(
    body: RegisterDriverIn,
    actor: deps.ActorDep,
    drivers: Annotated[object, Depends(deps.drivers)],
    users: Annotated[object, Depends(deps.users)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    """A passenger applies to drive.

    Deliberately open to any signed-in user: applying is not a privilege.
    Working is, and that still needs documents and an administrator.
    """
    use_case = RegisterDriver(
        drivers=drivers, users=users, audit=audit,
        clock=deps.clock(), new_id=deps.new_id,
    )
    driver_id = use_case.execute(
        RegisterDriverCommand(
            user_id=actor.user_id,
            actor_id=actor.user_id,
            home_district_id=body.home_district_id,
        )
    )
    return ok({"driver_id": driver_id, "approval_status": DocumentStatus.PENDING.value})


@router.get("/driver/documents")
def my_documents(
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    documents: Annotated[object, Depends(deps.driver_documents)],
    settings: Annotated[object, Depends(deps.app_settings)],
) -> dict:
    driver = drivers.find_by_user(actor.user_id)
    if driver is None:
        raise NotFoundError(error_codes.DRIVER_NOT_FOUND, user_id=actor.user_id)
    return ok(_checklist(driver, documents, settings).model_dump())


@router.post("/driver/documents")
async def upload_document(
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    documents: Annotated[object, Depends(deps.driver_documents)],
    settings: Annotated[object, Depends(deps.app_settings)],
    audit: Annotated[object, Depends(deps.audit)],
    file: Annotated[UploadFile, File()],
    document_type_code: Annotated[str, Form()],
    expires_on: Annotated[date | None, Form()] = None,
) -> dict:
    use_case = UploadDriverDocument(
        drivers=drivers, documents=documents, storage=deps.file_storage(),
        settings=settings, audit=audit, clock=deps.clock(), new_id=deps.new_id,
    )
    result = use_case.execute(
        UploadDocumentCommand(
            driver_user_id=actor.user_id,
            document_type_code=document_type_code.strip().upper(),
            content=await file.read(),
            declared_content_type=file.content_type,
            expires_on=expires_on,
        )
    )
    payload = asdict(result)
    payload["status"] = result.status.value
    payload.pop("uploaded_at", None)
    return ok(UploadedOut(**payload).model_dump())


@router.get("/driver/documents/{document_id}/file")
def my_document_file(
    document_id: str,
    actor: Annotated[deps.Actor, Depends(deps.require_driver)],
    drivers: Annotated[object, Depends(deps.drivers)],
    documents: Annotated[object, Depends(deps.driver_documents)],
) -> Response:
    """A driver may read only their own documents."""
    driver = drivers.find_by_user(actor.user_id)
    row = documents.get(document_id)
    if driver is None or row.driver_id != driver.id:
        # The same answer whether it belongs to someone else or does not exist,
        # so the endpoint cannot be used to discover document ids.
        raise NotFoundError(error_codes.DOCUMENT_NOT_FOUND, id=document_id)
    return _file_response(row)


# -- the reviewer's side -------------------------------------------------

@router.get("/admin/drivers/{driver_id}/documents")
def driver_documents_for_review(
    driver_id: str,
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    drivers: Annotated[object, Depends(deps.drivers)],
    documents: Annotated[object, Depends(deps.driver_documents)],
    settings: Annotated[object, Depends(deps.app_settings)],
) -> dict:
    driver = drivers.get(driver_id)
    return ok(_checklist(driver, documents, settings).model_dump())


@router.get("/admin/documents/{document_id}/file")
def document_file(
    document_id: str,
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    documents: Annotated[object, Depends(deps.driver_documents)],
) -> Response:
    """Staff may read any driver document, through this check and no other way."""
    return _file_response(documents.get(document_id))


@router.post("/admin/documents/{document_id}/review")
def review_document(
    document_id: str,
    body: ReviewIn,
    actor: Annotated[deps.Actor, Depends(deps.require_operations)],
    drivers: Annotated[object, Depends(deps.drivers)],
    documents: Annotated[object, Depends(deps.driver_documents)],
    settings: Annotated[object, Depends(deps.app_settings)],
    audit: Annotated[object, Depends(deps.audit)],
) -> dict:
    use_case = ReviewDriverDocument(
        drivers=drivers, documents=documents, settings=settings,
        audit=audit, clock=deps.clock(),
    )
    result = use_case.execute(
        ReviewDocumentCommand(
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


def _file_response(row) -> Response:
    """Serve the bytes, and make sure nothing caches or indexes them.

    These are identity documents: a shared proxy or a browser cache holding one
    is a leak that outlives the request.
    """
    stored = deps.file_storage().get(row.file_key)
    return Response(
        content=stored.content,
        media_type=stored.content_type,
        headers={
            "Cache-Control": "no-store, private",
            "Content-Disposition": f'inline; filename="{row.document_type_code.lower()}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )

