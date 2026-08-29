package af.velro.data.api

import kotlinx.serialization.Serializable

/**
 * Wire shapes.
 *
 * Separate from the domain entities on purpose: three shapes, three purposes --
 * wire (these), business (`:domain`), storage (Room entities). A field renamed
 * on the server changes one mapper here, not every screen.
 *
 * JSON is snake_case throughout, matching the server and the database, so a
 * field name is never translated in three places.
 */

@Serializable
data class MoneyDto(val amount_minor: Long, val currency: String)

// -- auth ---------------------------------------------------------------

@Serializable
data class RequestOtpRequest(val phone: String, val locale: String = "fa-AF")

@Serializable
data class RequestOtpResponse(
    val expires_in_seconds: Int,
    val resend_after_seconds: Int,
    val debug_code: String? = null,
)

@Serializable
data class VerifyOtpRequest(
    val phone: String,
    val code: String,
    val device_id: String? = null,
    val locale: String = "fa-AF",
)

@Serializable
data class RefreshRequest(val refresh_token: String, val device_id: String? = null)

@Serializable
data class SessionDto(
    val user_id: String,
    val access_token: String,
    val refresh_token: String,
    val roles: List<String>,
    val is_new_user: Boolean,
    val expires_in_seconds: Int,
)

@Serializable
data class ProfileDto(
    val id: String,
    val phone: String,
    val full_name: String? = null,
    val locale: String,
    val status: String,
    val roles: List<String>,
)

@Serializable
data class UpdateProfileRequest(val full_name: String? = null, val locale: String? = null)

// -- geography ----------------------------------------------------------

@Serializable
data class DistrictDto(
    val id: String,
    val code: String,
    val name: String,
    val alternative_name: String? = null,
    val province_id: String,
    val latitude: Double? = null,
    val longitude: Double? = null,
)

@Serializable
data class VillageDto(
    val id: String,
    val code: String,
    val name: String,
    val district_id: String,
    val latitude: Double? = null,
    val longitude: Double? = null,
)

@Serializable
data class StationDto(
    val id: String,
    val code: String,
    val name: String,
    val village_id: String,
    val district_id: String,
    val is_primary: Boolean = false,
    val description: String? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
    val distance_m: Int? = null,
)

@Serializable
data class DestinationDto(
    val id: String,
    val code: String,
    val name: String,
    val kind: String,
    val parent_id: String? = null,
    val district_id: String? = null,
    val station_id: String? = null,
    val sort_order: Int = 0,
)

@Serializable
data class DestinationGroupDto(
    val id: String,
    val code: String,
    val name: String,
    val kind: String,
    val children: List<DestinationDto> = emptyList(),
)

@Serializable
data class GeoSnapshotDto(
    val version: String,
    val districts: List<DistrictDto>,
    val villages: List<VillageDto>,
    val stations: List<StationDto>,
    val destinations: List<DestinationDto>,
)

@Serializable
data class SearchResultDto(
    val kind: String,
    val id: String,
    val code: String,
    val name: String,
    val district_id: String,
    val village_id: String? = null,
    val matched_alias: String? = null,
)

// -- booking ------------------------------------------------------------

@Serializable
data class SearchTripsRequest(
    val origin_station_id: String,
    val destination_id: String,
    val departure_after: String? = null,
    val seat_count: Int = 1,
    val ride_kind: String? = null,
)

@Serializable
data class TripOptionDto(
    val trip_id: String,
    val number: String,
    val route_id: String,
    val ride_kind: String,
    val scheduled_departure_at: String,
    val seats_available: Int,
    val seat_capacity: Int,
    val fare_total: MoneyDto? = null,
    val fare_per_seat: MoneyDto? = null,
    val status: String,
    val has_driver: Boolean,
)

@Serializable
data class BookSeatsRequest(
    val trip_id: String,
    val seat_count: Int,
    val pickup_station_id: String,
    val dropoff_destination_id: String,
    val payment_method: String = "CASH",
    val passenger_note: String? = null,
)

@Serializable
data class BookingDto(
    val id: String,
    val number: String,
    val trip_id: String,
    val status: String,
    val ride_kind: String,
    val seat_count: Int,
    val seat_numbers: List<Int>,
    val pickup_station_id: String,
    val dropoff_destination_id: String,
    val fare_total: MoneyDto,
    val payment_method: String,
    val verification_code: String? = null,
    val created_at: String? = null,
)

@Serializable
data class CancelBookingRequest(
    val reason_code: String = "PASSENGER_CANCELLED",
    val note: String? = null,
)

@Serializable
data class CancelBookingResponse(
    val booking_id: String,
    val status: String,
    val seats_released: Int,
    val fee: MoneyDto,
)

@Serializable
data class RateTripRequest(
    val score: Int,
    val comment: String? = null,
    val booking_id: String? = null,
)

@Serializable
data class RateTripResponse(
    val rating_id: String,
    val ratee_user_id: String,
    val score: Int,
)

// -- driver -------------------------------------------------------------

@Serializable
data class DriverStatusRequest(val availability: String)

@Serializable
data class VehicleDto(
    val id: String,
    val vehicle_type_code: String,
    val plate_number: String,
    val seat_capacity: Int,
    val brand: String? = null,
    val model: String? = null,
    val colour: String? = null,
    val status: String,
)

@Serializable
data class DriverProfileDto(
    val id: String,
    val user_id: String,
    val full_name: String? = null,
    val approval_status: String,
    val availability: String,
    val rating_average: Double? = null,
    val rating_count: Int = 0,
    val completed_trips: Int = 0,
    val vehicle: VehicleDto? = null,
    val missing_documents: List<String> = emptyList(),
)

@Serializable
data class TripSummaryDto(
    val id: String,
    val number: String,
    val status: String,
    val ride_kind: String,
    val scheduled_departure_at: String,
    val origin_station_id: String,
    val destination_id: String,
    val seat_capacity: Int,
    val seats_available: Int,
    val driver_id: String? = null,
    val vehicle_id: String? = null,
)

@Serializable
data class ManifestEntryDto(
    val booking_id: String,
    val number: String,
    val status: String,
    val seat_count: Int,
    val pickup_station_id: String,
    val dropoff_destination_id: String,
)

@Serializable
data class CurrentTripDto(
    val trip: TripSummaryDto,
    val manifest: List<ManifestEntryDto> = emptyList(),
)

@Serializable
data class AdvanceTripRequest(val target: String)

@Serializable
data class AdvanceTripResponse(
    val trip_id: String,
    val status: String,
    val bookings_advanced: Int,
    val driver_earning: MoneyDto? = null,
    val platform_commission: MoneyDto? = null,
)

@Serializable
data class VerifyPassengerRequest(val code: String)

@Serializable
data class VerifyPassengerResponse(
    val booking_id: String,
    val number: String,
    val passenger_name: String? = null,
    val seat_numbers: List<Int>,
    val status: String,
)

@Serializable
data class LocationPingRequest(
    val latitude: String,
    val longitude: String,
    val heading_degrees: Int? = null,
    val accuracy_m: Int? = null,
    val recorded_at: String? = null,
)

@Serializable
data class EarningsDto(
    val available: MoneyDto,
    val pending: MoneyDto,
    val lifetime_earned: MoneyDto,
    val lifetime_commission: MoneyDto,
    val completed_trips: Int,
)

@Serializable
data class OfferDto(
    val offer_id: String,
    val expires_at: String,
    val trip: TripSummaryDto,
)
