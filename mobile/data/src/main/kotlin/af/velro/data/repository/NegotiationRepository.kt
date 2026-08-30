package af.velro.data.repository

import af.velro.data.api.ApiResult
import af.velro.data.api.FareOfferDto
import af.velro.data.api.OfferFareRequest
import af.velro.data.api.RequestRideRequest
import af.velro.data.api.ResponseMapper
import af.velro.data.api.RideRequestDto
import af.velro.data.api.VelroApi
import af.velro.domain.FareOffer
import af.velro.domain.FareOfferStatus
import af.velro.domain.MoneyValue
import af.velro.domain.RideRequest
import af.velro.domain.RideRequestStatus
import af.velro.domain.enumOrNull
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Agreeing a fare, section 89.
 *
 * Not cached. A price is only worth showing while it can still be accepted, and
 * an offer read from disk is one a driver may have withdrawn an hour ago --
 * which on a screen about money is worse than showing nothing.
 */
@Singleton
class NegotiationRepository @Inject constructor(
    private val api: VelroApi,
    private val mapper: ResponseMapper,
) {

    suspend fun ask(
        originStationId: String,
        destinationId: String,
        passengerCount: Int,
        offeredFareMinor: Long,
        note: String? = null,
        /** Null means now. The server treats an absent value the same way. */
        requestedFor: Instant? = null,
        /** Null means one way. */
        returnFor: Instant? = null,
    ): ApiResult<RideRequest> =
        mapper.call {
            api.requestRide(
                RequestRideRequest(
                    origin_station_id = originStationId,
                    destination_id = destinationId,
                    passenger_count = passengerCount,
                    offered_fare_minor = offeredFareMinor,
                    note = note?.trim()?.ifBlank { null },
                    requested_for = requestedFor?.toString(),
                    return_for = returnFor?.toString(),
                )
            )
        }.map(::toDomain)

    suspend fun myRequests(): ApiResult<List<RideRequest>> =
        mapper.call { api.myRideRequests() }.map { it.map(::toDomain) }

    suspend fun cancel(requestId: String): ApiResult<Unit> =
        mapper.call { api.cancelRideRequest(requestId) }.map { }

    suspend fun accept(offerId: String): ApiResult<AcceptedRide> =
        mapper.call { api.acceptOffer(offerId) }.map {
            AcceptedRide(
                tripId = it.trip_id,
                bookingId = it.booking_id,
                bookingNumber = it.booking_number,
                verificationCode = it.verification_code,
                agreedFare = MoneyValue(it.agreed_fare.amount_minor, it.agreed_fare.currency),
            )
        }

    // -- the driver's side ---------------------------------------------

    suspend fun openRequests(stationId: String? = null): ApiResult<List<RideRequest>> =
        mapper.call { api.openRideRequests(stationId) }.map { it.map(::toDomain) }

    suspend fun offer(
        requestId: String,
        amountMinor: Long,
        note: String? = null,
    ): ApiResult<FareOffer> =
        mapper.call {
            api.offerFare(
                requestId,
                OfferFareRequest(amountMinor, note?.trim()?.ifBlank { null }),
            )
        }.map(::toDomain)

    suspend fun withdraw(offerId: String): ApiResult<Unit> =
        mapper.call { api.withdrawOffer(offerId) }.map { }

    suspend fun myOffers(): ApiResult<List<FareOffer>> =
        mapper.call { api.myFareOffers() }.map { it.map(::toDomain) }

    data class AcceptedRide(
        val tripId: String,
        val bookingId: String,
        val bookingNumber: String,
        val verificationCode: String,
        val agreedFare: MoneyValue,
    )

    private fun toDomain(dto: FareOfferDto) = FareOffer(
        id = dto.id,
        rideRequestId = dto.ride_request_id,
        driverId = dto.driver_id,
        amount = MoneyValue(dto.amount.amount_minor, dto.amount.currency),
        status = enumOrNull<FareOfferStatus>(dto.status) ?: FareOfferStatus.OFFERED,
        note = dto.note,
        createdAt = dto.created_at.toInstantOrNull(),
        driverName = dto.driver_name,
        driverRating = dto.driver_rating,
        driverTrips = dto.driver_trips,
        vehiclePlate = dto.vehicle_plate,
        vehicleDescription = dto.vehicle_description,
    )

    private fun toDomain(dto: RideRequestDto) = RideRequest(
        id = dto.id,
        status = enumOrNull<RideRequestStatus>(dto.status) ?: RideRequestStatus.OPEN,
        originStationId = dto.origin_station_id,
        originStationName = dto.origin_station_name,
        destinationId = dto.destination_id,
        destinationName = dto.destination_name,
        passengerCount = dto.passenger_count,
        offeredFare = MoneyValue(dto.offered_fare.amount_minor, dto.offered_fare.currency),
        agreedFare = dto.agreed_fare?.let { MoneyValue(it.amount_minor, it.currency) },
        note = dto.note,
        requestedFor = dto.requested_for.toInstantOrNull(),
        returnFor = dto.return_for?.toInstantOrNull(),
        expiresAt = dto.expires_at.toInstantOrNull(),
        createdAt = dto.created_at.toInstantOrNull(),
        tripId = dto.trip_id,
        offers = dto.offers.map(::toDomain),
        passengerName = dto.passenger_name,
        alreadyOffered = dto.already_offered,
    )
}

private fun String?.toInstantOrNull(): Instant? =
    this?.takeIf { it.isNotBlank() }?.let { runCatching { Instant.parse(it) }.getOrNull() }
