"""Drivers and vehicles.

A driver who has not been approved cannot receive work. That is enforced here,
in one predicate, rather than by whichever screen happens to remember to check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from domain.enums import (
    DocumentStatus,
    DriverApprovalStatus,
    DriverAvailability,
    VehicleStatus,
)
from shared import error_codes
from shared.errors import ConflictError, ValidationError


@dataclass(slots=True)
class DriverDocument:
    id: str
    driver_id: str
    document_type_code: str        # LICENSE, NATIONAL_ID, VEHICLE_REGISTRATION, ...
    file_key: str
    status: DocumentStatus = DocumentStatus.PENDING
    expires_on: date | None = None
    verified_by: str | None = None
    verified_at: datetime | None = None
    rejection_reason: str | None = None
    uploaded_at: datetime | None = None

    def is_valid_on(self, on: date) -> bool:
        if self.status is not DocumentStatus.VERIFIED:
            return False
        return self.expires_on is None or self.expires_on >= on


# Eastern Arabic-Indic digits appear on plates typed on an Afghan keyboard.
_EASTERN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalise_plate(plate: str) -> str:
    """The comparison form of a number plate.

    Two people entering the same vehicle as "PRW-1234", "prw 1234" and
    "PRW ۱۲۳۴" have entered one vehicle. Uniqueness on the raw string would
    accept all three, and the platform would then have three vehicles that are
    really one -- with three drivers able to be dispatched in it.

    The plate is stored as typed; only the comparison is normalised, exactly as
    village names are.
    """
    folded = plate.strip().upper().translate(_EASTERN_DIGITS)
    return "".join(ch for ch in folded if ch.isalnum())


@dataclass(slots=True)
class Vehicle:
    id: str
    driver_id: str
    vehicle_type_code: str
    plate_number: str
    seat_capacity: int
    brand: str | None = None
    model: str | None = None
    year: int | None = None
    colour: str | None = None
    status: VehicleStatus = VehicleStatus.PENDING

    def __post_init__(self) -> None:
        if self.seat_capacity <= 0:
            raise ValidationError(
                error_codes.VEHICLE_CAPACITY_INVALID, capacity=self.seat_capacity
            )
        if not self.plate_number.strip():
            raise ValidationError(error_codes.VEHICLE_PLATE_INVALID, reason="empty")
        if len(self.plate_key) < 4:
            # Short enough to be a typo rather than a plate. Afghan plates carry
            # a province code and a number.
            raise ValidationError(
                error_codes.VEHICLE_PLATE_INVALID,
                reason="too_short",
                plate_number=self.plate_number,
            )
        if self.year is not None and not 1950 <= self.year <= 2100:
            raise ValidationError(error_codes.VALIDATION_FAILED, field="year", value=self.year)

    @property
    def plate_key(self) -> str:
        """What uniqueness is decided on."""
        return normalise_plate(self.plate_number)

    @property
    def is_usable(self) -> bool:
        return self.status is VehicleStatus.ACTIVE

    def assert_usable(self) -> None:
        if not self.is_usable:
            raise ConflictError(
                error_codes.VEHICLE_SUSPENDED, vehicle_id=self.id, status=str(self.status)
            )

    def passenger_capacity(self) -> int:
        """Seats a passenger may occupy -- the driver's seat is not for sale."""
        return self.seat_capacity


def _uploaded_after(candidate: DriverDocument, existing: DriverDocument) -> bool:
    """Compare by upload time, falling back to nothing rather than guessing.

    A document with no recorded upload time never displaces one that has one.
    """
    if candidate.uploaded_at is None:
        return False
    if existing.uploaded_at is None:
        return True
    return candidate.uploaded_at > existing.uploaded_at


@dataclass(slots=True)
class Driver:
    id: str
    user_id: str
    approval_status: DriverApprovalStatus = DriverApprovalStatus.PENDING
    availability: DriverAvailability = DriverAvailability.OFFLINE
    rating_sum: int = 0
    rating_count: int = 0
    completed_trips: int = 0
    home_district_id: str | None = None
    home_station_id: str | None = None
    approved_at: datetime | None = None
    approved_by: str | None = None
    suspended_reason: str | None = None
    documents: list[DriverDocument] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.approval_status, DriverApprovalStatus):
            self.approval_status = DriverApprovalStatus(self.approval_status)
        if not isinstance(self.availability, DriverAvailability):
            self.availability = DriverAvailability(self.availability)

    # -- reputation -------------------------------------------------------

    @property
    def rating_average(self) -> float | None:
        """Presentation only. Never used in a money calculation."""
        if self.rating_count == 0:
            return None
        return round(self.rating_sum / self.rating_count, 2)

    def record_rating(self, score: int) -> None:
        if not 1 <= score <= 5:
            raise ValidationError(error_codes.RATING_OUT_OF_RANGE, score=score)
        self.rating_sum += score
        self.rating_count += 1

    # -- eligibility ------------------------------------------------------

    @property
    def is_approved(self) -> bool:
        return self.approval_status is DriverApprovalStatus.APPROVED

    def assert_can_work(self) -> None:
        """The single gate every dispatch path goes through."""
        if self.approval_status is DriverApprovalStatus.SUSPENDED:
            raise ConflictError(error_codes.DRIVER_SUSPENDED, driver_id=self.id)
        if not self.is_approved:
            raise ConflictError(
                error_codes.DRIVER_NOT_APPROVED,
                driver_id=self.id,
                status=str(self.approval_status),
            )

    def assert_can_accept(self) -> None:
        self.assert_can_work()
        if self.availability is DriverAvailability.OFFLINE:
            raise ConflictError(error_codes.DRIVER_OFFLINE, driver_id=self.id)
        if self.availability is DriverAvailability.ON_TRIP:
            raise ConflictError(error_codes.DRIVER_ALREADY_ON_TRIP, driver_id=self.id)

    def current_documents(self) -> dict[str, DriverDocument]:
        """The newest upload of each type.

        Only the newest counts. A driver who replaces a licence is presenting
        the new photograph, so the superseded one -- verified though it was --
        must not satisfy the requirement. Otherwise an administrator could
        approve someone whose current licence nobody has looked at.
        """
        newest: dict[str, DriverDocument] = {}
        for document in self.documents:
            existing = newest.get(document.document_type_code)
            if existing is None or _uploaded_after(document, existing):
                newest[document.document_type_code] = document
        return newest

    def missing_documents(self, required: frozenset[str], *, on: date) -> frozenset[str]:
        current = self.current_documents()
        held = {
            code for code, document in current.items() if document.is_valid_on(on)
        }
        return frozenset(required - held)

    def assert_documents_current(self, required: frozenset[str], *, on: date) -> None:
        """Every required document verified and not expired, today.

        Approval is a moment; a licence is a period. Checking the documents only
        when the driver is approved means a driver approved in Hamal is still
        approved in Jadi with a licence that ran out in Saratan -- carrying
        passengers on a permit no longer valid, with the platform's word behind
        them. This is the check that has to run every time work starts.

        Fails closed. If the caller did not load the documents, every required
        code comes back expired and the driver is stopped: a loud bug, rather
        than an unlicensed driver quietly let through.
        """
        stale = self.missing_documents(required, on=on)
        if stale:
            raise ConflictError(
                error_codes.DRIVER_DOCUMENTS_EXPIRED,
                driver_id=self.id,
                documents=sorted(stale),
            )

    def approve(self, *, by: str, at: datetime, required_documents: frozenset[str]) -> None:
        missing = self.missing_documents(required_documents, on=at.date())
        if missing:
            raise ConflictError(
                error_codes.DRIVER_DOCUMENTS_INCOMPLETE,
                driver_id=self.id,
                missing=sorted(missing),
            )
        self.approval_status = DriverApprovalStatus.APPROVED
        self.approved_at = at
        self.approved_by = by
        self.suspended_reason = None

    def suspend(self, reason: str) -> None:
        self.approval_status = DriverApprovalStatus.SUSPENDED
        self.availability = DriverAvailability.OFFLINE
        self.suspended_reason = reason

    def go_online(self) -> None:
        self.assert_can_work()
        if self.availability is DriverAvailability.OFFLINE:
            self.availability = DriverAvailability.ONLINE

    def go_offline(self) -> None:
        if self.availability is DriverAvailability.ON_TRIP:
            raise ConflictError(error_codes.DRIVER_ALREADY_ON_TRIP, driver_id=self.id)
        self.availability = DriverAvailability.OFFLINE
