package af.velro.domain

/**
 * Lifecycle enumerations, mirroring the server.
 *
 * The values are the wire strings, so a status crossing the network needs no
 * translation table. The canonical definitions live in
 * `docs/domain/lifecycles.json`; both this module and the Python domain are
 * tested against that file, so a rule changed in one language and not the other
 * fails a build.
 */

enum class TripStatus {
    SCHEDULED,
    REQUESTED,
    DRIVER_ASSIGNED,
    DRIVER_ARRIVING,
    ARRIVED_AT_PICKUP,
    BOARDING,
    IN_TRANSIT,
    ARRIVED,
    COMPLETED,
    CANCELLED,
    EXPIRED,
    NO_DRIVER_AVAILABLE,
}

enum class BookingStatus {
    PENDING,
    CONFIRMED,
    DRIVER_ASSIGNED,
    READY,
    ONBOARD,
    COMPLETED,
    CANCELLED,
    NO_SHOW,
}

enum class SeatStatus { AVAILABLE, RESERVED, OCCUPIED, BLOCKED }

enum class SettlementStatus { PENDING, PROCESSING, PAID, REJECTED }

/**
 * Money moving out to a driver, or in from one. Mirrors the server: cash fares
 * mean the driver holds the money and owes the platform its share, so a
 * collection is the ordinary case.
 */
enum class SettlementDirection { PAYOUT, COLLECTION }

enum class RideKind { PRIVATE, SHARED }

enum class DriverApprovalStatus { PENDING, APPROVED, REJECTED, SUSPENDED }

enum class DriverAvailability { OFFLINE, ONLINE, BUSY, ON_TRIP }

enum class PaymentMethod { CASH, MOBILE_WALLET, CARD, CORPORATE }

enum class Locale(val tag: String) {
    ENGLISH("en"),
    DARI("fa-AF"),
    PASHTO("ps"),
    ;

    val isRtl: Boolean get() = this != ENGLISH

    companion object {
        fun fromTag(tag: String): Locale =
            entries.firstOrNull { it.tag == tag } ?: DARI
    }
}

/** How a value that came off the network is turned into an enum without crashing. */
inline fun <reified T : Enum<T>> enumOrNull(value: String?): T? =
    value?.let { raw -> enumValues<T>().firstOrNull { it.name == raw } }
