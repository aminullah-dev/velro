"""Drivers and vehicles.

A driver who has not been approved cannot receive work. That is enforced here,
in one predicate, rather than by whichever screen happens to remember to check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from domain import documents
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
        return documents.is_valid_on(self, on)


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
class VehicleDocument:
    """A permit belonging to the car itself -- جواز سیر and its kin.

    Structurally the same as a DriverDocument and deliberately a separate type:
    the two hang off different aggregates, and one table with a nullable owner
    is how a vehicle's permit ends up counting for a driver who does not own
    that vehicle any more. The *rules* are shared (see domain.documents); only
    the ownership differs.
    """

    id: str
    vehicle_id: str
    document_type_code: str        # VEHICLE_REGISTRATION, ...
    file_key: str
    status: DocumentStatus = DocumentStatus.PENDING
    expires_on: date | None = None
    verified_by: str | None = None
    verified_at: datetime | None = None
    rejection_reason: str | None = None
    uploaded_at: datetime | None = None

    def is_valid_on(self, on: date) -> bool:
        return documents.is_valid_on(self, on)


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
    # جواز سیر and anything else the vehicle itself must carry. The permit
    # belongs to the car, not to whoever is driving it: a driver with two
    # vehicles holds two of them, and one cannot stand in for the other.
    documents: list[VehicleDocument] = field(default_factory=list)

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

    # -- paperwork --------------------------------------------------------

    def current_documents(self) -> dict[str, VehicleDocument]:
        return documents.newest_of_each_type(self.documents)

    def missing_documents(self, required: frozenset[str], *, on: date) -> frozenset[str]:
        return documents.outstanding(self.documents, required, on=on)

    def assert_documents_current(self, required: frozenset[str], *, on: date) -> None:
        """Every permit this vehicle needs, verified and not run out, today.

        Same shape as the driver's gate and for the same reason: activation is a
        moment, a جواز سیر is a period. A car approved in Hamal is still ACTIVE
        in Jadi with a permit that ran out in Saratan.

        Fails closed. A caller that did not load the documents stops the car.
        """
        stale = self.missing_documents(required, on=on)
        if stale:
            raise ConflictError(
                error_codes.VEHICLE_DOCUMENTS_EXPIRED,
                vehicle_id=self.id,
                documents=sorted(stale),
            )

    def activate(self, *, required_documents: frozenset[str], on: date) -> None:
        """Put the car into service.

        The permit is checked here rather than trusted to whoever clicks the
        button: an administrator approving a vehicle is approving the car they
        were shown the paperwork for.
        """
        missing = self.missing_documents(required_documents, on=on)
        if missing:
            raise ConflictError(
                error_codes.VEHICLE_DOCUMENTS_INCOMPLETE,
                vehicle_id=self.id,
                missing=sorted(missing),
            )
        self.status = VehicleStatus.ACTIVE


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
        """The newest upload of each type."""
        return documents.newest_of_each_type(self.documents)

    def missing_documents(self, required: frozenset[str], *, on: date) -> frozenset[str]:
        return documents.outstanding(self.documents, required, on=on)

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
