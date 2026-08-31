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
    /** Present only while the journey is still ahead. See BookingOut. */
    val driverPhone: String? = null,
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
    /** The name, so a driver can be told where to drive. */
    val originStationName: String? = null,
    val destinationId: String,
    val destinationName: String? = null,
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

    /**
     * Whether the driver is holding VELRO's money rather than the other way
     * round.
     *
     * Read from the whole position, never from `available` alone. On a cash
     * trip the fare is handed over at the vehicle, so the platform's share
     * stays in the driver's pocket and the wallet goes negative. Opening a
     * settlement then moves that debt out of `available` and into `pending` --
     * so a rule written against `available` flips to "you owe nothing" at the
     * exact moment the driver acts on the debt, while the screen behind it
     * still shows the money. Both surfaces ask this now.
     */
    val owesPlatform: Boolean get() = owed.amountMinor < 0

    /**
     * The figure to headline, always positive.
     *
     * What he can take out, or what he is holding for us -- the label beside
     * it says which, and the sign never reaches the screen.
     */
    val headlineAmount: MoneyValue
        get() =
            if (owesPlatform) MoneyValue(-owed.amountMinor, owed.currency)
            else available
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


/**
 * What to dial when something is wrong.
 *
 * `BUILT_IN` is compiled into the app on purpose. The server copy is better --
 * an operator can change it without a release -- but the moment these are
 * needed is the moment the network is least likely to be there, and an app
 * that has to ask before it can show 119 is an app that shows nothing.
 *
 * Deliberately not @Serializable. `:domain` is a kotlin("jvm") module with no
 * dependencies on its main classpath at all -- that is the property which makes
 * the layering rule compiler-checked rather than review-checked. Serialising
 * this is the data layer's job, through its own DTO.
 */
data class SafetyContacts(
    val emergencyNumbers: List<String> = emptyList(),
    /** Null when VELRO has no real number configured. A dead button is worse. */
    val velroNumber: String? = null,
    val categories: List<String> = emptyList(),
    val urgentCategories: List<String> = emptyList(),
) {
    companion object {
        /** Afghan police and ambulance. Also the default in the backend settings. */
        val BUILT_IN = SafetyContacts(
            emergencyNumbers = listOf("119", "100"),
            velroNumber = null,
            // The order is the triage, exactly as it is in the operator's
            // queue: SAFETY first because it means "I am in danger", then the
            // other urgent ones, and "Something else" last. An offline handset
            // shows this list, so getting it right here matters as much as on
            // the server.
            categories = listOf(
                "SAFETY", "DRIVER_CONDUCT", "PASSENGER_CONDUCT",
                "APP_PROBLEM", "FARE_DISPUTE", "LOST_ITEM", "VEHICLE_CONDITION",
                "OTHER",
            ),
            urgentCategories = listOf("SAFETY", "DRIVER_CONDUCT", "PASSENGER_CONDUCT"),
        )
    }
}


/**
 * A report the person raised, and the conversation on it.
 *
 * Internal notes never arrive here: the server filters them before they leave.
 * The app could not enforce that even if it wanted to, which is the point --
 * an operator's "this driver has three of these" must not be one client bug
 * away from the driver's screen.
 */
data class SupportMessage(
    val id: String,
    val isFromReporter: Boolean,
    val body: String,
    val sentAt: java.time.Instant,
)

data class SupportTicket(
    val id: String,
    val reference: String,
    val categoryCode: String,
    val status: TicketStatus,
    val isUrgent: Boolean = false,
    val createdAt: java.time.Instant,
    val messages: List<SupportMessage> = emptyList(),
) {
    /** Whether a reply from here would be accepted. Mirrors the server's rule. */
    val canReply: Boolean get() = status != TicketStatus.CLOSED

    /** VELRO has said something the person may not have read yet. */
    val hasAnswer: Boolean get() = messages.any { !it.isFromReporter }
}

/**
 * How a driver's money moved over one day, week or month.
 *
 * [net] arrives from the server rather than being computed here. The app and
 * the office must never disagree about a figure a driver checks against the
 * cash in his pocket, and two subtractions in two languages is how they start
 * to.
 */
data class EarningsBucket(
    /** First day of the bucket. Formatted by the UI, which knows the calendar. */
    val startsOn: String,
    val earned: MoneyValue,
    val commission: MoneyValue,
    val net: MoneyValue,
    val trips: Int,
)

enum class EarningsPeriod { DAY, WEEK, MONTH }

data class EarningsSummary(
    val period: EarningsPeriod,
    /** Oldest first, gaps filled with zeroes so a chart keeps even spacing. */
    val buckets: List<EarningsBucket>,
) {
    /** The tallest bar, for scaling. Zero when nothing was earned at all. */
    val peakNetMinor: Long get() = buckets.maxOfOrNull { it.net.amountMinor } ?: 0L
    val totalNetMinor: Long get() = buckets.sumOf { it.net.amountMinor }
    val totalTrips: Int get() = buckets.sumOf { it.trips }
}

/**
 * A passenger, as their own account.
 *
 * Distinct from [DriverProfile], which is about a person's standing as a
 * supplier. This is about the account: who it belongs to, what language it
 * speaks, and how long it has been open.
 */
data class UserProfile(
    val id: String,
    val phone: String,
    val fullName: String?,
    val locale: Locale,
    val completedTrips: Int,
    /** ISO instant the account was opened, or null on an older record. */
    val memberSince: String?,
    /** What drivers have scored them, or null before anybody has. */
    val ratingAverage: Double? = null,
    val ratingCount: Int = 0,
)
