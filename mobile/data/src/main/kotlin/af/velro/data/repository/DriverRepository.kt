package af.velro.data.repository

import af.velro.data.api.AdvanceTripRequest
import af.velro.data.api.ApiResult
import af.velro.data.api.DriverStatusRequest
import af.velro.data.api.IdempotencyKeys
import af.velro.data.api.LocationPingRequest
import af.velro.data.api.ResponseMapper
import af.velro.data.api.VelroApi
import af.velro.data.api.VerifyPassengerRequest
import af.velro.data.db.VelroDatabase
import af.velro.domain.DriverAvailability
import af.velro.domain.DriverProfile
import af.velro.domain.Earnings
import af.velro.domain.Lifecycles
import af.velro.domain.MoneyValue
import af.velro.domain.TripStatus
import af.velro.domain.TripSummary
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class DriverRepository @Inject constructor(
    private val api: VelroApi,
    private val db: VelroDatabase,
    private val mapper: ResponseMapper,
) {

    suspend fun profile(): ApiResult<DriverProfile> =
        mapper.call { api.driverProfile() }.map { it.toDomain() }

    suspend fun setAvailability(availability: DriverAvailability): ApiResult<String> =
        mapper.call { api.setDriverStatus(DriverStatusRequest(availability.name)) }
            .map { it["availability"] ?: availability.name }

    suspend fun offers(): ApiResult<List<TripSummary>> =
        mapper.call { api.offers() }.map { list -> list.map { it.trip.toDomain() } }

    suspend fun accept(tripId: String, driverId: String): ApiResult<Unit> =
        mapper.call {
            api.acceptTrip(tripId, IdempotencyKeys.forAccept(tripId, driverId))
        }.map { }

    /**
     * Move the trip to its next state.
     *
     * The app checks the transition table before calling so an impossible
     * button is greyed out rather than producing a 409 the driver has to read
     * on a bad connection. The server remains authoritative.
     */
    suspend fun advance(
        tripId: String,
        from: TripStatus,
        to: TripStatus,
        /** Only sent when `to` is CANCELLED, and required there. */
        reasonCode: String? = null,
        note: String? = null,
    ): ApiResult<AdvanceOutcome> {
        require(Lifecycles.trip.can(from, to)) {
            "the app must not offer ${from.name} -> ${to.name}"
        }
        return mapper.call {
            api.advanceTrip(tripId, AdvanceTripRequest(to.name, reasonCode, note))
        }
            .map { response ->
                AdvanceOutcome(
                    status = af.velro.domain.enumOrNull<TripStatus>(response.status) ?: to,
                    bookingsAdvanced = response.bookings_advanced,
                    driverEarning = response.driver_earning?.toDomain(),
                    platformCommission = response.platform_commission?.toDomain(),
                )
            }
    }

    suspend fun verifyPassenger(tripId: String, code: String): ApiResult<VerifiedPassenger> =
        mapper.call { api.verifyPassenger(tripId, VerifyPassengerRequest(code)) }
            .map {
                VerifiedPassenger(
                    bookingNumber = it.number,
                    passengerName = it.passenger_name,
                    seatNumbers = it.seat_numbers,
                )
            }

    suspend fun currentTrip(): ApiResult<CurrentAssignment?> =
        mapper.callNullable { api.currentTrip() }.map { dto ->
            dto?.let {
                CurrentAssignment(
                    trip = it.trip.toDomain(),
                    manifest = it.manifest.map { entry ->
                        ManifestEntry(
                            bookingId = entry.booking_id,
                            number = entry.number,
                            status = entry.status,
                            seatCount = entry.seat_count,
                            pickupStationId = entry.pickup_station_id,
                            dropoffDestinationId = entry.dropoff_destination_id,
                            passengerName = entry.passenger_name,
                            passengerPhone = entry.passenger_phone,
                            fareTotalMinor = entry.fare_total_minor,
                            fareCurrency = entry.fare_currency,
                        )
                    },
                )
            }
        }

    suspend fun earnings(): ApiResult<Earnings> =
        mapper.call { api.earnings() }.map { it.toDomain() }

    /** Fire-and-forget: a dropped ping is replaced by the next one. */
    suspend fun pingLocation(
        latitude: Double,
        longitude: Double,
        headingDegrees: Int? = null,
        accuracyMetres: Int? = null,
    ): ApiResult<Unit> =
        mapper.call {
            api.pingLocation(
                LocationPingRequest(
                    latitude = latitude.toString(),
                    longitude = longitude.toString(),
                    heading_degrees = headingDegrees,
                    accuracy_m = accuracyMetres,
                )
            )
        }.map { }
}

data class AdvanceOutcome(
    val status: TripStatus,
    val bookingsAdvanced: Int,
    val driverEarning: MoneyValue?,
    val platformCommission: MoneyValue?,
)

data class VerifiedPassenger(
    val bookingNumber: String,
    val passengerName: String?,
    val seatNumbers: List<Int>,
)

data class CurrentAssignment(
    val trip: TripSummary,
    val manifest: List<ManifestEntry>,
)

data class ManifestEntry(
    val bookingId: String,
    val number: String,
    val status: String,
    val seatCount: Int,
    val pickupStationId: String,
    val dropoffDestinationId: String,
    /** Who he is looking for at the station, and how to reach them. */
    val passengerName: String? = null,
    val passengerPhone: String? = null,
    /** The fare he agreed, which he collects in cash. */
    val fareTotalMinor: Int? = null,
    val fareCurrency: String? = null,
)
