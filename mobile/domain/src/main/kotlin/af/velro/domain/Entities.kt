package af.velro.domain

import java.time.Instant

/**
 * Domain entities.
 *
 * Plain data classes with no framework, no Android, no serialisation
 * annotations. The wire shapes live in `:data` and map onto these; keeping the
 * two apart is what lets the API change a field name without a screen noticing.
 */

data class District(
    val id: String,
    val code: String,
    val name: String,
    val alternativeName: String? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
)

data class Village(
    val id: String,
    val code: String,
    val name: String,
    val districtId: String,
    /** The other names this place is known by, section 7. */
    val alternativeNames: List<String> = emptyList(),
    val latitude: Double? = null,
    val longitude: Double? = null,
) {
    /**
     * Whether this village answers to what the passenger typed.
     *
     * Checks the aliases too: someone looking for رحمانیه must find آب بالا,
     * or the alias is only a search key rather than a name the village has.
     */
    fun matches(query: String): Boolean =
        PlaceNames.matches(name, query) ||
            alternativeNames.any { PlaceNames.matches(it, query) }
}

data class Station(
    val id: String,
    val code: String,
    val name: String,
    val villageId: String,
    val districtId: String,
    val isPrimary: Boolean = false,
    val description: String? = null,
    val latitude: Double? = null,
    val longitude: Double? = null,
    /** Only set by the "nearby" query; absent when browsing. */
    val distanceMetres: Int? = null,
)

data class Destination(
    val id: String,
    val code: String,
    val name: String,
    val kind: String,
    val parentId: String? = null,
    val sortOrder: Int = 0,
)

/** Kabul with Khair Khana Mina and Jada beneath it, as section 16 requires. */
data class DestinationGroup(
    val id: String,
    val code: String,
    val name: String,
    val kind: String,
    val children: List<Destination> = emptyList(),
) {
    /** A group whose only real choices are its children is not itself selectable. */
    val isChoosableItself: Boolean get() = children.isEmpty()
}

data class TripOption(
    val tripId: String,
    val number: String,
    val routeId: String,
    val rideKind: RideKind,
    val scheduledDepartureAt: Instant,
    val seatsAvailable: Int,
    val seatCapacity: Int,
    val fareTotal: MoneyValue?,
    val farePerSeat: MoneyValue?,
    val status: TripStatus,
    val hasDriver: Boolean,
) {
    fun canSeat(passengers: Int): Boolean =
        seatsAvailable >= passengers && status in Lifecycles.bookableTripStatuses
}

data class Booking(
    val id: String,
    val number: String,
    val tripId: String,
    val status: BookingStatus,
    val rideKind: RideKind,
    val seatCount: Int,
    val seatNumbers: List<Int>,
    val pickupStationId: String,
    val dropoffDestinationId: String,
    val fareTotal: MoneyValue,
    val paymentMethod: PaymentMethod,
    /** Present only for the passenger who owns it. It is what boards them. */
    val verificationCode: String? = null,
    val createdAt: Instant? = null,
    /**
     * The fare as it was quoted when the booking was made.
     *
     * Kept with the booking rather than recomputed: a price change afterwards
     * must never alter a receipt the passenger already holds.
     */
    val fareBreakdown: List<FareComponent> = emptyList(),
    /**
     * Where the journey ran, recorded with the booking.
     *
     * The geography cache can answer this too, but only once it has been
     * downloaded -- and a station renamed or retired later would then make an
     * old receipt describe a journey the passenger never took.
     */
    val pickupStationName: String? = null,
    val dropoffDestinationName: String? = null,
    val tripNumber: String? = null,
    val scheduledDepartureAt: Instant? = null,
    val driverName: String? = null,
    val vehiclePlate: String? = null,
    val vehicleDescription: String? = null,
    val completedAt: Instant? = null,
    val cancelledAt: Instant? = null,
    val cancellationReasonCode: String? = null,
    val cancellationFee: MoneyValue? = null,
) {
    val isActive: Boolean get() = !Lifecycles.booking.isTerminal(status)
    val canCancel: Boolean get() = status in Lifecycles.cancellableBookingStatuses
    val canRate: Boolean get() = status == BookingStatus.COMPLETED

    /** A journey still ahead: the passenger may still need to board it. */
    val isUpcoming: Boolean get() = isActive

    /**
     * Whether the components account for the total.
     *
     * A receipt whose lines do not add up is worse than one with no lines,
     * so the screen shows the breakdown only when this holds.
     */
    val breakdownExplainsTotal: Boolean
        get() = fareBreakdown.isNotEmpty() &&
            fareBreakdown.sumOf { it.total.amountMinor } == fareTotal.amountMinor
}

/** One line of a receipt. The key is a message key, never a sentence. */
data class FareComponent(
    val key: String,
    val amount: MoneyValue,
    val quantity: Int = 1,
) {
    val total: MoneyValue get() = MoneyValue(amount.amountMinor * quantity, amount.currency)
}

data class TripSummary(
    val id: String,
    val number: String,
    val status: TripStatus,
    val rideKind: RideKind,
    val scheduledDepartureAt: Instant,
    val originStationId: String,
    val destinationId: String,
    val seatCapacity: Int,
    val seatsAvailable: Int,
    val driverId: String? = null,
    val vehicleId: String? = null,
)

/**
 * The car, section 26.
 *
 * A driver and a vehicle are approved separately: the papers say the person may
 * drive, this says the car may carry passengers. Both must pass before work can
 * start, which is why `canWork` on the profile consults this status too.
 */
data class Vehicle(
    val id: String,
    val vehicleTypeCode: String,
    val plateNumber: String,
    val seatCapacity: Int,
    val brand: String? = null,
    val model: String? = null,
    val year: Int? = null,
    val colour: String? = null,
    val status: VehicleStatus,
) {
    val isReadyForWork: Boolean get() = status == VehicleStatus.ACTIVE

    /** "Toyota Corolla 2012", skipping whatever the driver did not fill in. */
    val describedAs: String
        get() = listOfNotNull(brand, model, year?.toString()).joinToString(" ")
}

enum class VehicleStatus { PENDING, ACTIVE, SUSPENDED, RETIRED }

/** A type an operator configured, section 105 -- not an enum in the app, so
 *  adding one does not require every driver to update before they can pick it. */
data class VehicleType(
    val code: String,
    val nameKey: String,
    val defaultSeatCapacity: Int,
)

data class DriverProfile(
    val id: String,
    val userId: String,
    val fullName: String?,
    val approvalStatus: DriverApprovalStatus,
    val availability: DriverAvailability,
    val ratingAverage: Double?,
    val ratingCount: Int,
    val completedTrips: Int,
    val vehicle: Vehicle?,
    val missingDocuments: List<String> = emptyList(),
) {
    /**
     * The single gate the driver app checks before showing any work.
     *
     * Mirrors the server rule so the app can explain *why* rather than showing
     * an empty screen; the server still refuses independently.
     */
    val canWork: Boolean
        get() = approvalStatus == DriverApprovalStatus.APPROVED &&
            missingDocuments.isEmpty() &&
            vehicle != null &&
            vehicle.isReadyForWork

    /**
     * Which half of the gate is still shut.
     *
     * The two halves fail for different reasons and are fixed on different
     * screens, so telling a driver only "not approved" sends them to the wrong
     * one -- or to a phone call.
     */
    val blockedByVehicle: Boolean
        get() = !canWork && (vehicle == null || !vehicle.isReadyForWork)

    val isOnline: Boolean
        get() = availability == DriverAvailability.ONLINE ||
            availability == DriverAvailability.ON_TRIP
}

data class Earnings(
    val available: MoneyValue,
    val pending: MoneyValue,
    val lifetimeEarned: MoneyValue,
    val lifetimeCommission: MoneyValue,
    val lifetimePaid: MoneyValue = MoneyValue(0, available.currency),
    val completedTrips: Int,
) {
    /**
     * Everything owed but not yet handed over.
     *
     * A driver with a payout in flight sees a smaller "available" figure and
     * would otherwise think money went missing, so both buckets are shown and
     * this is what they add up to.
     */
    val owed: MoneyValue get() = available + pending
}

/**
 * One line of the wallet ledger.
 *
 * The balance a driver is shown is a projection; this is the record it is
 * projected from. Each entry carries the balance it produced so a driver can
 * follow the arithmetic down the screen rather than being asked to trust a
 * single total.
 */
data class LedgerEntry(
    val id: String,
    val kind: LedgerKind,
    val amount: MoneyValue,
    val balanceAfter: MoneyValue,
    val createdAt: Instant,
    val bookingId: String? = null,
    val tripId: String? = null,
    val settlementId: String? = null,
    val note: String? = null,
) {
    val isCredit: Boolean get() = amount.amountMinor > 0
}

enum class LedgerKind {
    TRIP_EARNING, COMMISSION, SETTLEMENT, ADJUSTMENT, CANCELLATION_FEE, UNKNOWN,
}

data class Settlement(
    val id: String,
    val reference: String,
    val amount: MoneyValue,
    val direction: SettlementDirection = SettlementDirection.PAYOUT,
    val status: SettlementStatus,
    val periodStart: String,
    val periodEnd: String,
    val paidAt: Instant? = null,
    val rejectionReason: String? = null,
) {
    /** Still holding the driver's money. */
    val isOpen: Boolean
        get() = status == SettlementStatus.PENDING || status == SettlementStatus.PROCESSING
}

/**
 * What the payout button is allowed to do, decided by the server.
 *
 * The rule lives in one place. If the app worked it out from the balance and
 * the minimum on its own, the two would disagree the first time an operator
 * changed the minimum.
 */
data class PayoutOptions(
    val minimum: MoneyValue,
    val canRequest: Boolean,
    /**
     * Which way money moves next.
     *
     * Cash fares mean the driver holds the passenger's money and owes VELRO its
     * share, so COLLECTION is the ordinary case and PAYOUT the exception. The
     * server decides it; the app must not infer it from the sign of a number it
     * might be showing stale.
     */
    val direction: SettlementDirection = SettlementDirection.PAYOUT,
    val amountOwed: MoneyValue = MoneyValue(0, minimum.currency),
    val amountWithdrawable: MoneyValue = MoneyValue(0, minimum.currency),
    val openReference: String? = null,
    val history: List<Settlement> = emptyList(),
) {
    val owesPlatform: Boolean get() = direction == SettlementDirection.COLLECTION
}

data class Session(
    val userId: String,
    val accessToken: String,
    val refreshToken: String,
    val roles: List<String>,
    val isNewUser: Boolean,
    val expiresInSeconds: Int,
) {
    val isDriver: Boolean get() = "DRIVER" in roles
    val isPassenger: Boolean get() = "PASSENGER" in roles
}


// -- driver documents ---------------------------------------------------

enum class DocumentStatus { PENDING, VERIFIED, REJECTED, EXPIRED }

data class DriverDocument(
    val id: String,
    val documentTypeCode: String,
    val status: DocumentStatus,
    val expiresOn: String? = null,
    val rejectionReason: String? = null,
    val uploadedAt: java.time.Instant,
    val isCurrent: Boolean,
)

/**
 * What a driver still has to send, and where each item stands.
 *
 * Only the current upload of each type counts: a driver who replaces a licence
 * is presenting the new photograph, so the superseded one -- verified though it
 * may have been -- no longer satisfies the requirement.
 */
data class DocumentChecklist(
    val required: List<String>,
    val missing: List<String>,
    val documents: List<DriverDocument>,
    val approvalStatus: String,
    val canWork: Boolean,
) {
    fun currentFor(typeCode: String): DriverDocument? =
        documents.firstOrNull { it.documentTypeCode == typeCode && it.isCurrent }

    val isComplete: Boolean get() = missing.isEmpty()

    val awaitingReview: Boolean
        get() = isComplete && !canWork
}


/**
 * The car's own papers -- جواز سیر and its kin.
 *
 * Keyed by vehicle rather than by driver. A driver with two cars owes two
 * permits; while this was a driver document there was one slot for it and the
 * first car's permit certified the second.
 */
data class VehicleDocument(
    val id: String,
    val vehicleId: String,
    val documentTypeCode: String,
    val status: DocumentStatus,
    val expiresOn: String? = null,
    val rejectionReason: String? = null,
    val uploadedAt: java.time.Instant,
    val isCurrent: Boolean,
)

data class VehicleChecklist(
    val vehicleId: String,
    val plateNumber: String,
    val required: List<String>,
    val missing: List<String>,
    val documents: List<VehicleDocument>,
    val vehicleStatus: String,
    val canCarry: Boolean,
) {
    fun currentFor(typeCode: String): VehicleDocument? =
        documents.firstOrNull { it.documentTypeCode == typeCode && it.isCurrent }

    val isComplete: Boolean get() = missing.isEmpty()

    /** Everything sent, nothing approved yet -- the state that needs explaining. */
    val awaitingReview: Boolean
        get() = isComplete && !canCarry
}


/**
 * One message in the inbox.
 *
 * Carries a message key and a payload, never a rendered sentence: the server
 * does not know what language the reader has the app set to, and the same key
 * resolves in the panel and both apps.
 */
data class Notification(
    val id: String,
    val messageKey: String,
    val payload: Map<String, String> = emptyMap(),
    val tripId: String? = null,
    val bookingId: String? = null,
    val createdAt: java.time.Instant,
    val readAt: java.time.Instant? = null,
) {
    val isUnread: Boolean get() = readAt == null
}

data class NotificationInbox(
    val notifications: List<Notification> = emptyList(),
    val unread: Int = 0,
)
