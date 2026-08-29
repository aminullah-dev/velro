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
    val alternative_names: List<String> = emptyList(),
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
data class FareComponentDto(
    val key: String,
    val amount: MoneyDto,
    val quantity: Int = 1,
)

@Serializable
data class BookingDto(
    val id: String,
    val number: String,
    val trip_id: String,
    val trip_number: String? = null,
    val status: String,
    val ride_kind: String,
    val seat_count: Int,
    val seat_numbers: List<Int>,
    val pickup_station_id: String,
    val dropoff_destination_id: String,
    val pickup_station_name: String? = null,
    val dropoff_destination_name: String? = null,
    val fare_total: MoneyDto,
    val fare_breakdown: List<FareComponentDto> = emptyList(),
    val payment_method: String,
    val scheduled_departure_at: String? = null,
    val driver_name: String? = null,
    val vehicle_plate: String? = null,
    val vehicle_description: String? = null,
    val confirmed_at: String? = null,
    val boarded_at: String? = null,
    val completed_at: String? = null,
    val cancelled_at: String? = null,
    val cancellation_reason_code: String? = null,
    val cancellation_fee: MoneyDto? = null,
    val verification_code: String? = null,
    val created_at: String? = null,
)

@Serializable
data class BookingPageDto(
    val bookings: List<BookingDto> = emptyList(),
    val has_more: Boolean = false,
    val next_offset: Int = 0,
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
    val year: Int? = null,
    val colour: String? = null,
    val status: String,
)

@Serializable
data class VehicleTypeDto(
    val code: String,
    val name_key: String,
    val default_seat_capacity: Int,
)

@Serializable
data class RegisterVehicleRequest(
    val vehicle_type_code: String,
    val plate_number: String,
    val seat_capacity: Int? = null,
    val brand: String? = null,
    val model: String? = null,
    val year: Int? = null,
    val colour: String? = null,
)

@Serializable
data class RegisteredVehicleDto(
    val id: String,
    val plate_number: String,
    val status: String,
    val seat_capacity: Int,
    val replaced_id: String? = null,
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
data class AdvanceTripRequest(
    val target: String,
    /** Only read when target is CANCELLED. */
    val reason_code: String? = null,
    val note: String? = null,
)

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
    val lifetime_paid: MoneyDto? = null,
    val completed_trips: Int,
)

@Serializable
data class LedgerEntryDto(
    val id: String,
    val kind: String,
    val amount: MoneyDto,
    val balance_after: MoneyDto,
    val created_at: String,
    val booking_id: String? = null,
    val trip_id: String? = null,
    val settlement_id: String? = null,
    val note: String? = null,
)

@Serializable
data class LedgerPageDto(
    val entries: List<LedgerEntryDto> = emptyList(),
    val has_more: Boolean = false,
    val next_offset: Int = 0,
)

@Serializable
data class SettlementDto(
    val id: String,
    val reference: String,
    val amount: MoneyDto,
    val direction: String = "PAYOUT",
    val status: String,
    val period_start: String,
    val period_end: String,
    val paid_at: String? = null,
    val rejection_reason: String? = null,
    val driver_id: String,
    val driver_name: String? = null,
    val driver_phone: String? = null,
)

@Serializable
data class PayoutOptionsDto(
    val settlements: List<SettlementDto> = emptyList(),
    val minimum: MoneyDto,
    val direction: String = "PAYOUT",
    val amount_owed: MoneyDto? = null,
    val amount_withdrawable: MoneyDto? = null,
    val can_request: Boolean = false,
    val open_reference: String? = null,
)

@Serializable
data class RequestSettlementRequest(val amount_minor: Long? = null)

@Serializable
data class OfferDto(
    val offer_id: String,
    val expires_at: String,
    val trip: TripSummaryDto,
)


// -- driver documents ---------------------------------------------------

@Serializable
data class DocumentDto(
    val id: String,
    val document_type_code: String,
    val status: String,
    val expires_on: String? = null,
    val rejection_reason: String? = null,
    val uploaded_at: String,
    val reviewed_at: String? = null,
    val is_current: Boolean,
)

@Serializable
data class DocumentChecklistDto(
    val required: List<String>,
    val missing: List<String>,
    val documents: List<DocumentDto> = emptyList(),
    val approval_status: String,
    val can_work: Boolean,
)

@Serializable
data class UploadedDocumentDto(
    val id: String,
    val document_type_code: String,
    val status: String,
    val supersedes_id: String? = null,
)

@Serializable
data class RegisterDriverRequest(val home_district_id: String? = null)


// -- the inbox ----------------------------------------------------------

@Serializable
data class NotificationDto(
    val id: String,
    val message_key: String,
    val payload: Map<String, String> = emptyMap(),
    val channel: String,
    val delivery_status: String,
    val trip_id: String? = null,
    val booking_id: String? = null,
    val created_at: String,
    val read_at: String? = null,
)

@Serializable
data class InboxDto(
    val notifications: List<NotificationDto> = emptyList(),
    val unread: Int = 0,
)

@Serializable
data class MarkReadRequest(val ids: List<String> = emptyList())


// -- vehicle documents: جواز سیر, per car -------------------------------

@Serializable
data class VehicleDocumentDto(
    val id: String,
    val vehicle_id: String,
    val document_type_code: String,
    val status: String,
    val expires_on: String? = null,
    val rejection_reason: String? = null,
    val uploaded_at: String,
    val reviewed_at: String? = null,
    val is_current: Boolean,
)

@Serializable
data class VehicleChecklistDto(
    val vehicle_id: String,
    val plate_number: String,
    val required: List<String>,
    val missing: List<String>,
    val documents: List<VehicleDocumentDto> = emptyList(),
    val vehicle_status: String,
    val can_carry: Boolean,
)


// -- negotiated fares, section 89 ---------------------------------------

@Serializable
data class RequestRideRequest(
    val origin_station_id: String,
    val destination_id: String,
    val passenger_count: Int = 1,
    val offered_fare_minor: Long,
    val vehicle_type_code: String? = null,
    val note: String? = null,
)

@Serializable
data class OfferFareRequest(
    val amount_minor: Long,
    val note: String? = null,
)

@Serializable
data class FareOfferDto(
    val id: String,
    val ride_request_id: String,
    val driver_id: String,
    val amount: MoneyDto,
    val status: String,
    val note: String? = null,
    val created_at: String = "",
    val driver_name: String? = null,
    val driver_rating: Double? = null,
    val driver_trips: Int = 0,
    val vehicle_plate: String? = null,
    val vehicle_description: String? = null,
)

@Serializable
data class RideRequestDto(
    val id: String,
    val status: String,
    val origin_station_id: String,
    val origin_station_name: String? = null,
    val destination_id: String,
    val destination_name: String? = null,
    val passenger_count: Int,
    val offered_fare: MoneyDto,
    val agreed_fare: MoneyDto? = null,
    val note: String? = null,
    val expires_at: String = "",
    val created_at: String = "",
    val trip_id: String? = null,
    val offers: List<FareOfferDto> = emptyList(),
    val passenger_name: String? = null,
    val already_offered: Boolean = false,
)

@Serializable
data class AcceptedOfferDto(
    val ride_request_id: String,
    val trip_id: String,
    val trip_number: String,
    val booking_id: String,
    val booking_number: String,
    val verification_code: String,
    val driver_id: String,
    val agreed_fare: MoneyDto,
)
