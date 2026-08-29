"""Vehicle registration and approval, sections 26 and 52.

A driver records the vehicle they will actually carry passengers in. An
administrator checks it against the registration document and activates it.
Until then the driver is approved but cannot work, which the apps say plainly
rather than leaving them to guess.

Changing vehicle retires the old record rather than editing it. A trip that
happened last week was in a particular car with a particular plate, and a
passenger asking "which vehicle was I in" must still get the right answer.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.driver import Vehicle, normalise_plate
from domain.enums import ActorRole, VehicleStatus
from shared import error_codes
from shared.clock import Clock
from shared.errors import ConflictError, NotFoundError, ValidationError
from shared.ids import IdGenerator


@dataclass(frozen=True, slots=True)
class RegisterVehicleCommand:
    driver_user_id: str
    vehicle_type_code: str
    plate_number: str
    seat_capacity: int | None = None
    brand: str | None = None
    model: str | None = None
    year: int | None = None
    colour: str | None = None
    request_id: str | None = None


@dataclass(frozen=True, slots=True)
class RegisteredVehicle:
    id: str
    plate_number: str
    status: VehicleStatus
    seat_capacity: int
    replaced_id: str | None


class RegisterVehicle:
    def __init__(
        self, *, drivers, vehicles, vehicle_types, trips, audit,
        clock: Clock, new_id: IdGenerator,
    ) -> None:
        self._drivers = drivers
        self._vehicles = vehicles
        self._vehicle_types = vehicle_types
        self._trips = trips
        self._audit = audit
        self._clock = clock
        self._new_id = new_id

    def execute(self, cmd: RegisterVehicleCommand) -> RegisteredVehicle:
        driver = self._drivers.find_by_user(cmd.driver_user_id)
        if driver is None:
            raise NotFoundError(error_codes.DRIVER_NOT_FOUND, user_id=cmd.driver_user_id)

        # Vehicle types are rows, so an operator can add one without a deploy
        # (section 105). An unknown code is refused with the list of real ones.
        vehicle_type = self._vehicle_types.find_by_code(cmd.vehicle_type_code)
        if vehicle_type is None or not vehicle_type.is_active:
            raise ValidationError(
                error_codes.VEHICLE_TYPE_UNKNOWN,
                vehicle_type_code=cmd.vehicle_type_code,
                accepted=[t.code for t in self._vehicle_types.active()],
            )

        capacity = cmd.seat_capacity or vehicle_type.default_seat_capacity
        if capacity <= 0:
            raise ValidationError(error_codes.VEHICLE_CAPACITY_INVALID, capacity=capacity)

        # Validated as a domain object before anything is written, so a bad
        # plate never reaches the database.
        candidate = Vehicle(
            id=self._new_id(),
            driver_id=driver.id,
            vehicle_type_code=vehicle_type.code,
            # Upper-cased, separators kept. A plate is an identifier read off a
            # physical car, not a name, so canonicalising the case is correct --
            # a passenger checking "prw 9911" against a car that says PRW-9911
            # is being made to do work the product should have done.
            plate_number=cmd.plate_number.strip().upper(),
            seat_capacity=capacity,
            brand=(cmd.brand or "").strip() or None,
            model=(cmd.model or "").strip() or None,
            year=cmd.year,
            colour=(cmd.colour or "").strip() or None,
        )

        clash = self._vehicles.find_by_plate_key(candidate.plate_key)
        if clash is not None and clash.driver_id != driver.id:
            # Named rather than left to the database constraint: the driver
            # needs to know the plate is taken, not see a 500.
            raise ConflictError(
                error_codes.VEHICLE_PLATE_TAKEN, plate_number=candidate.plate_number
            )

        current = self._vehicles.current_for_driver(driver.id)

        # A vehicle in the middle of a trip cannot be swapped out from under the
        # passengers riding in it.
        in_flight = self._trips.active_for_driver(driver.id)
        if in_flight is not None:
            raise ConflictError(
                error_codes.DRIVER_ALREADY_ON_TRIP,
                driver_id=driver.id,
                trip_id=in_flight.id,
            )

        if current is not None and current.plate_key == candidate.plate_key:
            # Same vehicle, corrected details. Update in place and send it back
            # for review; there is no history worth preserving in a typo fix.
            before = {
                "brand": current.brand, "model": current.model,
                "colour": current.colour, "seat_capacity": current.seat_capacity,
            }
            current.vehicle_type_code = candidate.vehicle_type_code
            current.plate_number = candidate.plate_number
            current.seat_capacity = candidate.seat_capacity
            current.brand = candidate.brand
            current.model = candidate.model
            current.year = candidate.year
            current.colour = candidate.colour
            current.status = VehicleStatus.PENDING.value
            current.updated_by = cmd.driver_user_id
            self._vehicles.save(current)

            self._audit.write(
                "vehicle.updated",
                actor_id=cmd.driver_user_id,
                actor_role=ActorRole.DRIVER,
                entity_type="vehicle",
                entity_id=current.id,
                before=before,
                after={
                    "brand": candidate.brand, "model": candidate.model,
                    "colour": candidate.colour, "seat_capacity": candidate.seat_capacity,
                    "status": VehicleStatus.PENDING.value,
                },
                request_id=cmd.request_id,
            )
            return RegisteredVehicle(
                id=current.id,
                plate_number=current.plate_number,
                status=VehicleStatus.PENDING,
                seat_capacity=current.seat_capacity,
                replaced_id=None,
            )

        # A different vehicle. Retire the old record rather than overwrite it:
        # completed trips point at it, and their history must stay truthful.
        replaced_id = None
        if current is not None:
            current.status = VehicleStatus.RETIRED.value
            current.updated_by = cmd.driver_user_id
            self._vehicles.save(current)
            replaced_id = current.id

        row = self._vehicles.create(
            id=candidate.id,
            driver_id=driver.id,
            vehicle_type_code=candidate.vehicle_type_code,
            plate_number=candidate.plate_number,
            plate_key=candidate.plate_key,
            seat_capacity=candidate.seat_capacity,
            brand=candidate.brand,
            model=candidate.model,
            year=candidate.year,
            colour=candidate.colour,
            status=VehicleStatus.PENDING.value,
            created_by=cmd.driver_user_id,
        )
        self._vehicles.flush()

        self._audit.write(
            "vehicle.registered",
            actor_id=cmd.driver_user_id,
            actor_role=ActorRole.DRIVER,
            entity_type="vehicle",
            entity_id=row.id,
            after={
                "driver_id": driver.id,
                "plate_number": candidate.plate_number,
                "vehicle_type_code": candidate.vehicle_type_code,
                "seat_capacity": candidate.seat_capacity,
                "replaced": replaced_id,
            },
            request_id=cmd.request_id,
        )
        return RegisteredVehicle(
            id=row.id,
            plate_number=row.plate_number,
            status=VehicleStatus.PENDING,
            seat_capacity=row.seat_capacity,
            replaced_id=replaced_id,
        )


@dataclass(frozen=True, slots=True)
class DecideVehicleCommand:
    vehicle_id: str
    actor_id: str
    actor_role: ActorRole
    approve: bool
    reason: str | None = None
    request_id: str | None = None


class DecideVehicle:
    """An administrator activates or suspends a vehicle."""

    def __init__(
        self, *, vehicles, trips, audit, clock: Clock, documents=None, settings=None
    ) -> None:
        self._vehicles = vehicles
        self._trips = trips
        self._audit = audit
        self._clock = clock
        self._documents = documents
        self._settings = settings

    def execute(self, cmd: DecideVehicleCommand) -> VehicleStatus:
        row = self._vehicles.get(cmd.vehicle_id)
        before = row.status

        if row.status == VehicleStatus.RETIRED.value:
            raise ConflictError(
                error_codes.VEHICLE_SUSPENDED, vehicle_id=row.id, status=row.status
            )

        if cmd.approve:
            # The permit is checked here, not trusted to whoever clicks the
            # button. An administrator activating a car is saying its جواز سیر
            # was seen and is valid; if the paperwork is not actually verified,
            # this is where that has to stop -- afterwards the car is in the
            # dispatch pool and a passenger is involved.
            self._assert_papers_in_order(row)

        if not cmd.approve:
            # Suspending a vehicle mid-trip would strand its passengers.
            in_flight = self._trips.active_for_driver(row.driver_id)
            if in_flight is not None and in_flight.vehicle_id == row.id:
                raise ConflictError(
                    error_codes.DRIVER_ALREADY_ON_TRIP,
                    vehicle_id=row.id,
                    trip_id=in_flight.id,
                )

        row.status = (
            VehicleStatus.ACTIVE.value if cmd.approve else VehicleStatus.SUSPENDED.value
        )
        row.updated_by = cmd.actor_id
        self._vehicles.save(row)

        self._audit.write(
            "vehicle.approved" if cmd.approve else "vehicle.suspended",
            actor_id=cmd.actor_id,
            actor_role=cmd.actor_role,
            entity_type="vehicle",
            entity_id=row.id,
            before={"status": before},
            after={"status": row.status, "reason": cmd.reason},
            request_id=cmd.request_id,
        )
        return VehicleStatus(row.status)

    def _assert_papers_in_order(self, row) -> None:
        """Raises unless every required paper is verified and unexpired.

        The dependencies are optional so that callers which cannot activate a
        vehicle need not wire them -- but an *approval* without them would be
        an approval that checked nothing, so that combination raises rather
        than passing quietly.
        """
        if self._settings is None or self._documents is None:
            raise ConflictError(
                error_codes.VEHICLE_DOCUMENTS_INCOMPLETE,
                vehicle_id=row.id,
                reason="documents_not_loaded",
            )
        from application.use_cases.vehicle_documents import to_vehicle

        required = frozenset(self._settings.get_list("vehicle.required_documents", []))
        if not required:
            return
        vehicle = to_vehicle(row, self._documents.for_vehicle(row.id))
        missing = vehicle.missing_documents(required, on=self._clock.now().date())
        if missing:
            raise ConflictError(
                error_codes.VEHICLE_DOCUMENTS_INCOMPLETE,
                vehicle_id=row.id,
                missing=sorted(missing),
            )


def plate_key_of(plate: str) -> str:
    """Exposed for the repository, so one rule decides uniqueness."""
    return normalise_plate(plate)
