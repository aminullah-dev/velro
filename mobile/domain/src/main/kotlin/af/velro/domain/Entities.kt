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
    val latitude: Double? = null,
    val longitude: Double? = null,
)

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
) {
    val isActive: Boolean get() = !Lifecycles.booking.isTerminal(status)
    val canCancel: Boolean get() = status in Lifecycles.cancellableBookingStatuses
    val canRate: Boolean get() = status == BookingStatus.COMPLETED
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

data class Vehicle(
    val id: String,
    val vehicleTypeCode: String,
    val plateNumber: String,
    val seatCapacity: Int,
    val brand: String? = null,
    val model: String? = null,
    val colour: String? = null,
    val status: String,
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
            vehicle.status == "ACTIVE"

    val isOnline: Boolean
        get() = availability == DriverAvailability.ONLINE ||
            availability == DriverAvailability.ON_TRIP
}

data class Earnings(
    val available: MoneyValue,
    val pending: MoneyValue,
    val lifetimeEarned: MoneyValue,
    val lifetimeCommission: MoneyValue,
    val completedTrips: Int,
)

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
