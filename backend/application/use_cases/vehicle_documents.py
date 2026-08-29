"""The car's own papers: upload and review.

جواز سیر belongs to the vehicle. A driver with two cars holds two permits, and
the first cannot certify the second -- which is exactly what happened while this
was a driver document with one slot.

Structurally these mirror `driver_documents`, and the parts that must not drift
between them -- what counts as a valid document, which upload is the current one
-- are not copied: both go through `domain.documents`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from domain.driver import Vehicle, VehicleDocument
from domain.enums import ActorRole, DocumentStatus, VehicleStatus
from shared import error_codes
from shared.clock import Clock
from shared.errors import NotFoundError, ValidationError
from shared.ids import IdGenerator

DOCUMENTS_NAMESPACE = "documents"


@dataclass(frozen=True, slots=True)
class UploadVehicleDocumentCommand:
    vehicle_id: str
    driver_user_id: str
    document_type_code: str
    content: bytes
    expires_on: date | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class UploadedVehicleDocument:
    id: str
    vehicle_id: str
    document_type_code: str
    status: DocumentStatus
    uploaded_at: datetime
    supersedes_id: str | None


class UploadVehicleDocument:
    def __init__(
        self, *, drivers, vehicles, documents, storage, settings, audit,
        clock: Clock, new_id: IdGenerator,
    ) -> None:
        self._drivers = drivers
        self._vehicles = vehicles
        self._documents = documents
        self._storage = storage
        self._settings = settings
        self._audit = audit
        self._clock = clock
        self._new_id = new_id

    def execute(self, cmd: UploadVehicleDocumentCommand) -> UploadedVehicleDocument:
        from infrastructure.services.storage import validate_upload

        now = self._clock.now()

        driver = self._drivers.find_by_user(cmd.driver_user_id)
        if driver is None:
            raise NotFoundError(error_codes.DRIVER_NOT_FOUND, user_id=cmd.driver_user_id)

        vehicle_row = self._vehicles.get(cmd.vehicle_id)
        # Ownership is checked here rather than trusted from the path. Without
        # it any signed-in driver could attach a permit to anyone's car -- and
        # the permit is what an administrator approves the car on.
        if vehicle_row.driver_id != driver.id:
            raise NotFoundError(error_codes.VEHICLE_NOT_FOUND, vehicle_id=cmd.vehicle_id)

        accepted = set(self._settings.get_list("vehicle.required_documents", []))
        optional = set(self._settings.get_list("vehicle.optional_documents", []))
        if cmd.document_type_code not in accepted | optional:
            raise ValidationError(
                error_codes.DOCUMENT_TYPE_UNKNOWN,
                document_type_code=cmd.document_type_code,
                accepted=sorted(accepted | optional),
            )

        content_type = validate_upload(cmd.content)
        key = self._storage.put(
            cmd.content, content_type=content_type, namespace=DOCUMENTS_NAMESPACE
        )

        previous = self._documents.current_for(vehicle_row.id, cmd.document_type_code)

        row = self._documents.create(
            id=self._new_id(),
            vehicle_id=vehicle_row.id,
            document_type_code=cmd.document_type_code,
            file_key=key,
            status=DocumentStatus.PENDING.value,
            expires_on=cmd.expires_on,
            created_by=cmd.driver_user_id,
        )
        self._documents.flush()

        # An active car whose permit is replaced goes back to pending, exactly
        # as an approved driver does: the activation was for the papers that
        # were reviewed, not for the car in perpetuity.
        returned_to_pending = False
        if vehicle_row.status == VehicleStatus.ACTIVE.value:
            vehicle_row.status = VehicleStatus.PENDING.value
            self._vehicles.save(vehicle_row)
            returned_to_pending = True

        self._audit.write(
            "vehicle.document_uploaded",
            actor_id=cmd.driver_user_id,
            actor_role=ActorRole.DRIVER,
            entity_type="vehicle_document",
            entity_id=row.id,
            after={
                "vehicle_id": vehicle_row.id,
                "document_type_code": cmd.document_type_code,
                "supersedes": previous.id if previous else None,
                "returned_to_pending": returned_to_pending,
                # The file key is deliberately absent: it is the handle to a
                # scanned document and does not belong in an audit diff.
            },
            request_id=cmd.request_id,
        )
        return UploadedVehicleDocument(
            id=row.id,
            vehicle_id=vehicle_row.id,
            document_type_code=cmd.document_type_code,
            status=DocumentStatus.PENDING,
            uploaded_at=now,
            supersedes_id=previous.id if previous else None,
        )


@dataclass(frozen=True, slots=True)
class ReviewVehicleDocumentCommand:
    document_id: str
    actor_id: str
    actor_role: ActorRole
    verified: bool
    expires_on: date | None = None
    rejection_reason: str | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class ReviewVehicleDocumentResult:
    document_id: str
    vehicle_id: str
    status: DocumentStatus
    vehicle_now_complete: bool
    missing_documents: list[str]


class ReviewVehicleDocument:
    """An administrator accepts or refuses one of the car's papers.

    Refusing requires a reason, for the same reason it does on the driver's
    side: a driver told only "rejected" photographs the same thing again.
    """

    def __init__(self, *, vehicles, documents, settings, audit, clock: Clock) -> None:
        self._vehicles = vehicles
        self._documents = documents
        self._settings = settings
        self._audit = audit
        self._clock = clock

    def execute(self, cmd: ReviewVehicleDocumentCommand) -> ReviewVehicleDocumentResult:
        now = self._clock.now()
        row = self._documents.get(cmd.document_id)

        if not cmd.verified and not (cmd.rejection_reason or "").strip():
            raise ValidationError(error_codes.DOCUMENT_REJECTION_REASON_REQUIRED)

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

        vehicle_row = self._vehicles.get(row.vehicle_id)
        required = frozenset(self._settings.get_list("vehicle.required_documents", []))
        vehicle = to_vehicle(vehicle_row, self._documents.for_vehicle(row.vehicle_id))
        missing = vehicle.missing_documents(required, on=now.date())

        self._audit.write(
            "vehicle.document_reviewed",
            actor_id=cmd.actor_id,
            actor_role=cmd.actor_role,
            entity_type="vehicle_document",
            entity_id=row.id,
            before={"status": before},
            after={
                "status": row.status,
                "vehicle_id": row.vehicle_id,
                "document_type_code": row.document_type_code,
                "rejection_reason": row.rejection_reason,
            },
            request_id=cmd.request_id,
        )
        return ReviewVehicleDocumentResult(
            document_id=row.id,
            vehicle_id=row.vehicle_id,
            status=DocumentStatus(row.status),
            vehicle_now_complete=not missing,
            missing_documents=sorted(missing),
        )


def to_vehicle(row, document_rows) -> Vehicle:
    """The aggregate, with its papers.

    One mapper, used everywhere a vehicle's paperwork is judged. A second copy
    is how an endpoint goes on reporting nothing missing after the rule is
    corrected elsewhere.
    """
    return Vehicle(
        id=row.id,
        driver_id=row.driver_id,
        vehicle_type_code=row.vehicle_type_code,
        plate_number=row.plate_number,
        seat_capacity=row.seat_capacity,
        brand=row.brand,
        model=row.model,
        year=row.year,
        colour=row.colour,
        status=VehicleStatus(row.status),
        documents=[
            VehicleDocument(
                id=d.id,
                vehicle_id=d.vehicle_id,
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


def assert_vehicle_papers_current(vehicle_row, document_rows, settings, *, on: date) -> None:
    """The gate, in one place.

    Called from going online and from anywhere else a car is about to be put to
    work. Fails closed: no documents loaded means the car is stopped.
    """
    required = frozenset(settings.get_list("vehicle.required_documents", []))
    if not required:
        return
    to_vehicle(vehicle_row, document_rows).assert_documents_current(required, on=on)


__all__ = [
    "ReviewVehicleDocument",
    "ReviewVehicleDocumentCommand",
    "ReviewVehicleDocumentResult",
    "UploadVehicleDocument",
    "UploadVehicleDocumentCommand",
    "UploadedVehicleDocument",
    "assert_vehicle_papers_current",
    "to_vehicle",
]
