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
    /** The outbound leg, or the whole fare on a one-way journey. */
    val amount: MoneyValue,
    /** The way back, when the request asked for one. */
    val returnAmount: MoneyValue? = null,
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
    fun agreesWith(asking: MoneyValue): Boolean = total.amountMinor == asking.amountMinor

    /**
     * How this price compares with what was asked, as a signed difference.
     *
     * Shown rather than made the passenger work out: a column of amounts that
     * must be subtracted from a number higher up the screen is arithmetic
     * asked of someone standing at a roadside.
     */
    fun differenceFrom(asking: MoneyValue): MoneyValue =
        MoneyValue(total.amountMinor - asking.amountMinor, amount.currency)

    /**
     * What this offer costs, both legs together.
     *
     * Every comparison on the offers screen is against this, never against
     * the outbound alone: a driver answering 350 out and 300 back has named
     * 650, and a card that compared 350 with what was asked would tell the
     * passenger the cheaper driver is the dearer one.
     */
    val total: MoneyValue
        get() = returnAmount?.let {
            MoneyValue(amount.amountMinor + it.amountMinor, amount.currency)
        } ?: amount
}

data class RideRequest(
    val id: String,
    val status: RideRequestStatus,
    val originStationId: String,
    val originStationName: String? = null,
    val destinationId: String,
    val destinationName: String? = null,
    val passengerCount: Int,
    /** The outbound leg, or the whole fare on a one-way journey. */
    val offeredFare: MoneyValue,
    /** The way back, when one was asked for. */
    val returnFare: MoneyValue? = null,
    val agreedFare: MoneyValue? = null,
    val note: String? = null,
    /**
     * When the passenger wants to travel.
     *
     * Null for a request made before the field existed, and for one that means
     * "now" -- the two are the same thing to a reader, and neither should draw
     * a departure time on a card.
     */
    val requestedFor: Instant? = null,
    /**
     * When the passenger wants to come back, if they said.
     *
     * Null is one way, and most journeys are. A return is not a second
     * request: in Ghorband a car to Charikar or Kabul is hired for both legs
     * at one price, argued once, and the way back is usually a different day.
     */
    val returnFor: Instant? = null,
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
        // By the total, not the outbound leg. Sorted on the outbound alone,
        // a driver asking 300 out and 400 back would sit above one asking 350
        // and 300, and the list labelled cheapest-first would be leading with
        // the dearer journey.
        get() = offers.filter { it.isOpen }.sortedBy { it.total.amountMinor }

    /**
     * What the passenger offered for the whole journey.
     *
     * The figure every offer is compared against. `offeredFare` alone is the
     * outbound leg on a round trip, and comparing a driver's total with one
     * leg of the ask would make every reply look expensive.
     */
    val askingTotal: MoneyValue
        get() = returnFare?.let {
            MoneyValue(offeredFare.amountMinor + it.amountMinor, offeredFare.currency)
        } ?: offeredFare

    val isWaitingForOffers: Boolean get() = isOpen && liveOffers.isEmpty()
}
