from __future__ import annotations

from datetime import datetime

from pydantic import Field

from ui.api.schemas.common import MoneyOut, Schema


class SearchTripsIn(Schema):
    origin_station_id: str
    destination_id: str
    departure_after: datetime | None = None
    seat_count: int = Field(default=1, ge=1, le=8)
    ride_kind: str | None = Field(default=None, pattern=r"^(PRIVATE|SHARED)$")


class TripOptionOut(Schema):
    trip_id: str
    number: str
    route_id: str
    ride_kind: str
    scheduled_departure_at: datetime
    seats_available: int
    seat_capacity: int
    fare_total: MoneyOut | None
    fare_per_seat: MoneyOut | None
    status: str
    has_driver: bool


class BookSeatsIn(Schema):
    trip_id: str
    seat_count: int = Field(default=1, ge=1, le=8)
    pickup_station_id: str
    dropoff_destination_id: str
    payment_method: str = Field(default="CASH", pattern=r"^(CASH|MOBILE_WALLET|CARD|CORPORATE)$")
    passenger_note: str | None = Field(default=None, max_length=500)


class FareComponentOut(Schema):
    """One line of the receipt. The key is a message key, never a sentence:
    the passenger reads it in their own language, and a stored English phrase
    could not be retranslated later."""

    key: str
    amount: MoneyOut
    quantity: int


class BookingOut(Schema):
    id: str
    number: str
    trip_id: str
    trip_number: str | None = None
    status: str
    ride_kind: str
    seat_count: int
    seat_numbers: list[int]
    pickup_station_id: str
    dropoff_destination_id: str
    # The names as they are now. A receipt should say where the passenger
    # actually went even if a station is renamed or retired afterwards, and a
    # phone that has never downloaded the geography snapshot has no other way
    # to render them.
    pickup_station_name: str | None = None
    dropoff_destination_name: str | None = None
    fare_total: MoneyOut
    # The breakdown as it stood when the booking was made. A later price change
    # must never alter a receipt a passenger already holds.
    fare_breakdown: list[FareComponentOut] = Field(default_factory=list)
    payment_method: str
    scheduled_departure_at: datetime | None = None
    # Present only once a driver is assigned, which is most of what a passenger
    # wants from a receipt: who drove, and in what.
    driver_name: str | None = None
    vehicle_plate: str | None = None
    vehicle_description: str | None = None
    confirmed_at: datetime | None = None
    boarded_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    cancellation_reason_code: str | None = None
    cancellation_fee: MoneyOut | None = None
    # Shown only to the passenger who owns the booking, never in a list to
    # anyone else: it is what boards them.
    verification_code: str | None = None
    created_at: datetime | None = None


class CancelBookingIn(Schema):
    reason_code: str = Field(default="PASSENGER_CANCELLED", max_length=40)
    note: str | None = Field(default=None, max_length=500)


class CancelBookingOut(Schema):
    booking_id: str
    status: str
    seats_released: int
    fee: MoneyOut


class RateTripIn(Schema):
    score: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=1000)
    booking_id: str | None = None


class RateTripOut(Schema):
    rating_id: str
    ratee_user_id: str
    score: int
