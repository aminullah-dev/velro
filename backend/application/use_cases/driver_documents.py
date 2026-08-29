"""Driver documents: upload, review, approval.

Sections 27, 28 and 51. A driver cannot receive work until an administrator has
seen their licence, national identity card and vehicle registration and marked
each one verified. That gate lives in the domain entity, so no path here can
approve someone whose licence is missing however the request is shaped.

Re-uploading does not overwrite. The old row stays, so a driver can see why the
first attempt was rejected and an administrator can see what they originally
sent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from domain.driver import Driver, DriverDocument
from domain.enums import ActorRole, DocumentStatus, DriverApprovalStatus, DriverAvailability
from shared import error_codes
from shared.clock import Clock
from shared.errors import ConflictError, NotFoundError, PermissionError, ValidationError
from shared.ids import IdGenerator

DOCUMENTS_NAMESPACE = "driver-documents"


@dataclass(frozen=True, slots=True)
class UploadDocumentCommand:
    driver_user_id: str
    document_type_code: str
    content: bytes
    declared_content_type: str | None = None
    expires_on: date | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class UploadedDocument:
    id: str
    document_type_code: str
    status: DocumentStatus
    uploaded_at: datetime
    supersedes_id: str | None


class UploadDriverDocument:
    def __init__(
        self, *, drivers, documents, storage, settings, audit, clock: Clock, new_id: IdGenerator
    ) -> None:
        self._drivers = drivers
        self._documents = documents
        self._storage = storage
        self._settings = settings
        self._audit = audit
        self._clock = clock
        self._new_id = new_id

    def execute(self, cmd: UploadDocumentCommand) -> UploadedDocument:
        from infrastructure.services.storage import validate_upload

        now = self._clock.now()

        driver = self._drivers.find_by_user(cmd.driver_user_id)
        if driver is None:
            raise NotFoundError(error_codes.DRIVER_NOT_FOUND, user_id=cmd.driver_user_id)

        accepted = set(self._settings.get_list("driver.required_documents", []))
        optional = set(self._settings.get_list("driver.optional_documents", []))
        if cmd.document_type_code not in accepted | optional:
            raise ValidationError(
                error_codes.DOCUMENT_TYPE_UNKNOWN,
                document_type_code=cmd.document_type_code,
                accepted=sorted(accepted | optional),
            )

        # Validated before it is written: an unidentifiable upload never
        # reaches the disk.
        content_type = validate_upload(cmd.content)
        key = self._storage.put(
            cmd.content, content_type=content_type, namespace=DOCUMENTS_NAMESPACE
        )

        previous = self._documents.current_for(driver.id, cmd.document_type_code)

        row = self._documents.create(
            id=self._new_id(),
            driver_id=driver.id,
            document_type_code=cmd.document_type_code,
            file_key=key,
            status=DocumentStatus.PENDING.value,
            expires_on=cmd.expires_on,
            created_by=cmd.driver_user_id,
        )
        self._documents.flush()

        # A driver who was approved and then replaces a document goes back to
        # pending: the approval was for the documents that were reviewed, not
        # for the driver in perpetuity.
        returned_to_pending = False
        if driver.approval_status == DriverApprovalStatus.APPROVED.value:
            driver.approval_status = DriverApprovalStatus.PENDING.value
            driver.availability = DriverAvailability.OFFLINE.value
            self._drivers.save(driver)
            returned_to_pending = True

        self._audit.write(
            "driver.document_uploaded",
            actor_id=cmd.driver_user_id,
            actor_role=ActorRole.DRIVER,
            entity_type="driver_document",
            entity_id=row.id,
            after={
                "driver_id": driver.id,
                "document_type_code": cmd.document_type_code,
                "supersedes": previous.id if previous else None,
                "returned_to_pending": returned_to_pending,
                # The file key is deliberately absent: it is the handle to an
                # identity document and does not belong in an audit diff.
            },
            request_id=cmd.request_id,
        )
        return UploadedDocument(
            id=row.id,
            document_type_code=cmd.document_type_code,
            status=DocumentStatus.PENDING,
            uploaded_at=now,
            supersedes_id=previous.id if previous else None,
        )


@dataclass(frozen=True, slots=True)
class ReviewDocumentCommand:
    document_id: str
    actor_id: str
    actor_role: ActorRole
    verified: bool
    expires_on: date | None = None
    rejection_reason: str | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewDocumentResult:
    document_id: str
    driver_id: str
    status: DocumentStatus
    driver_now_complete: bool
    missing_documents: list[str]


class ReviewDriverDocument:
    """An administrator accepts or refuses one document.

    Refusing requires a reason. A driver told only "rejected" has to guess what
    to photograph again, and will usually send the same thing.
    """

    def __init__(self, *, drivers, documents, settings, audit, clock: Clock) -> None:
        self._drivers = drivers
        self._documents = documents
        self._settings = settings
        self._audit = audit
        self._clock = clock

    def execute(self, cmd: ReviewDocumentCommand) -> ReviewDocumentResult:
        now = self._clock.now()
        row = self._documents.get(cmd.document_id)

        if not cmd.verified and not (cmd.rejection_reason or "").strip():
            raise ValidationError(error_codes.DOCUMENT_REJECTION_REASON_REQUIRED)

        # Re-deciding is deliberately allowed: a mistaken rejection has to be
        # fixable, and the audit entry carries what the status was before.
        before = row.status
        row.status = (
            DocumentStatus.VERIFIED.value if cmd.verified else DocumentStatus.REJECTED.value
        )
        row.verified_by = cmd.actor_id
        row.verified_at = now
        row.rejection_reason = None if cmd.verified else cmd.rejection_reason
        if cmd.expires_on is not None:
            row.expires_on = cmd.expires_on
        self._documents.save(row)

        driver_row = self._drivers.get(row.driver_id)
        required = frozenset(self._settings.get_list("driver.required_documents", []))
        driver = _to_driver(driver_row, self._documents.for_driver(row.driver_id))
        missing = driver.missing_documents(required, on=now.date())

        self._audit.write(
            "driver.document_reviewed",
            actor_id=cmd.actor_id,
            actor_role=cmd.actor_role,
            entity_type="driver_document",
            entity_id=row.id,
            before={"status": before},
            after={
                "status": row.status,
                "driver_id": row.driver_id,
                "document_type_code": row.document_type_code,
                "rejection_reason": row.rejection_reason,
            },
            request_id=cmd.request_id,
        )
        return ReviewDocumentResult(
            document_id=row.id,
            driver_id=row.driver_id,
            status=DocumentStatus(row.status),
            driver_now_complete=not missing,
            missing_documents=sorted(missing),
        )


@dataclass(frozen=True, slots=True)
class RegisterDriverCommand:
    user_id: str
    actor_id: str
    home_district_id: str | None = None
    request_id: str | None = None


class RegisterDriver:
    """A passenger becomes a driver applicant.

    Creates the driver record in PENDING and grants the DRIVER role, which is
    what lets them reach the upload endpoints. It does not let them work --
    that needs documents and an administrator.
    """

    def __init__(self, *, drivers, users, audit, clock: Clock, new_id: IdGenerator) -> None:
        self._drivers = drivers
        self._users = users
        self._audit = audit
        self._clock = clock
        self._new_id = new_id

    def execute(self, cmd: RegisterDriverCommand) -> str:
        if cmd.user_id != cmd.actor_id:
            raise PermissionError(error_codes.PERMISSION_DENIED, user_id=cmd.user_id)

        existing = self._drivers.find_by_user(cmd.user_id)
        if existing is not None:
            raise ConflictError(
                error_codes.DRIVER_ALREADY_REGISTERED,
                user_id=cmd.user_id,
                driver_id=existing.id,
            )

        user = self._users.get(cmd.user_id)
        row = self._drivers.create(
            id=self._new_id(),
            user_id=user.id,
            approval_status=DriverApprovalStatus.PENDING.value,
            availability=DriverAvailability.OFFLINE.value,
            home_district_id=cmd.home_district_id,
            created_by=cmd.actor_id,
        )
        self._drivers.flush()
        self._users.grant_role(user.id, "DRIVER")

        self._audit.write(
            "driver.registered",
            actor_id=cmd.actor_id,
            actor_role=ActorRole.DRIVER,
            entity_type="driver",
            entity_id=row.id,
            after={"user_id": user.id, "approval_status": row.approval_status},
            request_id=cmd.request_id,
        )
        return row.id


def _to_driver(row, document_rows) -> Driver:
    return Driver(
        id=row.id,
        user_id=row.user_id,
        approval_status=DriverApprovalStatus(row.approval_status),
        availability=DriverAvailability(row.availability),
        rating_sum=row.rating_sum,
        rating_count=row.rating_count,
        completed_trips=row.completed_trips,
        documents=[
            DriverDocument(
                id=d.id,
                driver_id=d.driver_id,
                document_type_code=d.document_type_code,
                file_key=d.file_key,
                status=DocumentStatus(d.status),
                expires_on=d.expires_on,
                verified_by=d.verified_by,
                verified_at=d.verified_at,
                rejection_reason=d.rejection_reason,
                uploaded_at=d.created_at,
            )
            for d in document_rows
        ],
    )
