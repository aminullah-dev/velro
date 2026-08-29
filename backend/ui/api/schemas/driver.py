from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import Field

from ui.api.schemas.common import MoneyOut, Schema


class DriverStatusIn(Schema):
    availability: str = Field(pattern=r"^(ONLINE|OFFLINE)$")


class DriverProfileOut(Schema):
    id: str
    user_id: str
    full_name: str | None
    approval_status: str
    availability: str
    rating_average: float | None
    rating_count: int
    completed_trips: int
    vehicle: VehicleOut | None = None
    missing_documents: list[str] = Field(default_factory=list)


class VehicleOut(Schema):
    id: str
    vehicle_type_code: str
    plate_number: str
    seat_capacity: int
    brand: str | None = None
    model: str | None = None
    colour: str | None = None
    status: str


class AdvanceTripIn(Schema):
    target: str = Field(
        pattern=r"^(DRIVER_ARRIVING|ARRIVED_AT_PICKUP|BOARDING|IN_TRANSIT|ARRIVED|COMPLETED|CANCELLED)$"
    )
    # Only meaningful when target is CANCELLED. A cancellation with no recorded
    # reason cannot be told from any other: a driver whose car broke down and
    # one who simply changed their mind look identical afterwards, and the
    # second is the one that costs a passenger a morning.
    reason_code: str | None = Field(
        default=None,
        pattern=r"^(DRIVER_CANCELLED|VEHICLE_PROBLEM|WEATHER|OTHER)$",
    )
    note: str | None = Field(default=None, max_length=500)


class AdvanceTripOut(Schema):
    trip_id: str
    status: str
    bookings_advanced: int
    driver_earning: MoneyOut | None = None
    platform_commission: MoneyOut | None = None


class VerifyPassengerIn(Schema):
    code: str = Field(min_length=3, max_length=12)


class VerifyPassengerOut(Schema):
    booking_id: str
    number: str
    passenger_name: str | None
    seat_numbers: list[int]
    status: str


class LocationPingIn(Schema):
    latitude: Decimal
    longitude: Decimal
    heading_degrees: int | None = Field(default=None, ge=0, lt=360)
    accuracy_m: int | None = Field(default=None, ge=0)
    recorded_at: datetime | None = None


class EarningsOut(Schema):
    available: MoneyOut
    pending: MoneyOut
    lifetime_earned: MoneyOut
    lifetime_commission: MoneyOut
    # What has actually been handed over. Without it a driver who has been paid
    # sees only that their balance fell, with nothing saying where it went.
    lifetime_paid: MoneyOut
    completed_trips: int


class TripSummaryOut(Schema):
    id: str
    number: str
    status: str
    ride_kind: str
    scheduled_departure_at: datetime
    origin_station_id: str
    destination_id: str
    seat_capacity: int
    seats_available: int
    driver_id: str | None = None
    vehicle_id: str | None = None


DriverProfileOut.model_rebuild()
