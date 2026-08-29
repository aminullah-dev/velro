package af.velro.domain

import java.time.Instant

/**
 * Agreeing a fare, section 89.
 *
 * VELRO does not price a journey. Nobody knows how many kilometres separate two
 * villages in Ghorband, or which stretch of road is asphalt and which is dirt
 * that turns to mud in spring -- so the fare is what a passenger and a driver
 * agree, exactly as they agree it at the station today.
 */
enum class RideRequestStatus { OPEN, MATCHED, CANCELLED, EXPIRED }

enum class FareOfferStatus { OFFERED, ACCEPTED, DECLINED, WITHDRAWN, EXPIRED }

data class FareOffer(
    val id: String,
    val rideRequestId: String,
    val driverId: String,
    val amount: MoneyValue,
    val status: FareOfferStatus,
    val note: String? = null,
    val createdAt: Instant? = null,
    val driverName: String? = null,
    val driverRating: Double? = null,
    val driverTrips: Int = 0,
    val vehiclePlate: String? = null,
    val vehicleDescription: String? = null,
) {
    val isOpen: Boolean get() = status == FareOfferStatus.OFFERED

    /** Whether this driver simply agreed to the asking price. */
    fun agreesWith(asking: MoneyValue): Boolean = amount.amountMinor == asking.amountMinor

    /**
     * How this price compares with what was asked, as a signed difference.
     *
     * Shown rather than made the passenger work out: a column of amounts that
     * must be subtracted from a number higher up the screen is arithmetic
     * asked of someone standing at a roadside.
     */
    fun differenceFrom(asking: MoneyValue): MoneyValue =
        MoneyValue(amount.amountMinor - asking.amountMinor, amount.currency)
}

data class RideRequest(
    val id: String,
    val status: RideRequestStatus,
    val originStationId: String,
    val originStationName: String? = null,
    val destinationId: String,
    val destinationName: String? = null,
    val passengerCount: Int,
    val offeredFare: MoneyValue,
    val agreedFare: MoneyValue? = null,
    val note: String? = null,
    val expiresAt: Instant? = null,
    val createdAt: Instant? = null,
    val tripId: String? = null,
    val offers: List<FareOffer> = emptyList(),
    val passengerName: String? = null,
    /** Set on the driver's board: this driver has already named a price. */
    val alreadyOffered: Boolean = false,
) {
    val isOpen: Boolean get() = status == RideRequestStatus.OPEN

    /** Offers still awaiting the passenger's answer, cheapest first. */
    val liveOffers: List<FareOffer>
        get() = offers.filter { it.isOpen }.sortedBy { it.amount.amountMinor }

    val isWaitingForOffers: Boolean get() = isOpen && liveOffers.isEmpty()
}
