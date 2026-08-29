package af.velro.data.db

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

/**
 * The local cache.
 *
 * Offline-first is the assumption, not a feature: connectivity in Ghorband is
 * intermittent and the app has to be usable with none. Geography is cached in
 * full because it changes a few times a year, and the passenger's own bookings
 * are cached because "where is my seat" must be answerable in a valley with no
 * signal.
 *
 * Column names mirror the server's, so a support question can be answered by
 * looking at either side.
 */

@Entity(tableName = "districts")
data class DistrictEntity(
    @PrimaryKey val id: String,
    val code: String,
    val name: String,
    val alternativeName: String?,
    val provinceId: String,
    val latitude: Double?,
    val longitude: Double?,
)

@Entity(
    tableName = "villages",
    indices = [Index("districtId"), Index("name")],
)
data class VillageEntity(
    @PrimaryKey val id: String,
    val code: String,
    val name: String,
    val districtId: String,
    /**
     * Other names, newline-separated.
     *
     * Cached with the village because browsing is an offline operation: a
     * passenger in a valley with no signal must still find their village by
     * the name they use for it.
     */
    val alternativeNames: String = "",
    val latitude: Double?,
    val longitude: Double?,
)

@Entity(
    tableName = "stations",
    indices = [Index("villageId"), Index("districtId"), Index("name")],
)
data class StationEntity(
    @PrimaryKey val id: String,
    val code: String,
    val name: String,
    val villageId: String,
    val districtId: String,
    val isPrimary: Boolean,
    val description: String?,
    val latitude: Double?,
    val longitude: Double?,
)

@Entity(tableName = "destinations", indices = [Index("parentId")])
data class DestinationEntity(
    @PrimaryKey val id: String,
    val code: String,
    val name: String,
    val kind: String,
    val parentId: String?,
    val districtId: String?,
    val stationId: String?,
    val sortOrder: Int,
)

/** Which destinations a given origin can reach, so the choice works offline. */
@Entity(tableName = "station_destinations", primaryKeys = ["stationId", "destinationId"])
data class StationDestinationEntity(
    val stationId: String,
    val destinationId: String,
)

@Entity(tableName = "bookings", indices = [Index("tripId"), Index("createdAt")])
data class BookingEntity(
    @PrimaryKey val id: String,
    val number: String,
    val tripId: String,
    val status: String,
    val rideKind: String,
    val seatCount: Int,
    val seatNumbers: String,          // comma-separated; Room has no list type
    val pickupStationId: String,
    val dropoffDestinationId: String,
    val fareTotalMinor: Long,
    val fareTotalCurrency: String,
    /**
     * The receipt lines, as JSON.
     *
     * Cached rather than fetched, because a passenger asking what they paid is
     * often doing so precisely where there is no signal. Stored as text because
     * Room has no list type and a second table for a handful of lines that are
     * only ever read together would cost a join for nothing.
     */
    val fareBreakdown: String = "[]",
    val pickupStationName: String? = null,
    val dropoffDestinationName: String? = null,
    val paymentMethod: String,
    val tripNumber: String? = null,
    val scheduledDepartureAt: Long? = null,
    val driverName: String? = null,
    val vehiclePlate: String? = null,
    val vehicleDescription: String? = null,
    val completedAt: Long? = null,
    val cancelledAt: Long? = null,
    val cancellationReasonCode: String? = null,
    val cancellationFeeMinor: Long? = null,
    val verificationCode: String?,
    val createdAt: Long?,
    /**
     * PENDING until the server has confirmed it. A booking made offline is
     * shown to the passenger as pending rather than hidden, because the worst
     * outcome is someone believing they have no seat when they do.
     */
    val syncState: String = SyncState.SYNCED,
)

@Entity(tableName = "trips")
data class TripEntity(
    @PrimaryKey val id: String,
    val number: String,
    val status: String,
    val rideKind: String,
    val scheduledDepartureAt: Long,
    val originStationId: String,
    val destinationId: String,
    val seatCapacity: Int,
    val seatsAvailable: Int,
    val driverId: String?,
    val vehicleId: String?,
    val updatedAt: Long,
)

/**
 * Mutations made while offline, replayed in order by WorkManager.
 *
 * Every entry carries the idempotency key it will be sent with, so a replay
 * that the server already applied returns the original response instead of
 * creating a second booking.
 */
@Entity(tableName = "pending_operations", indices = [Index("createdAt")])
data class PendingOperationEntity(
    @PrimaryKey val id: String,
    val kind: String,
    val payload: String,
    val idempotencyKey: String,
    val createdAt: Long,
    val attempts: Int = 0,
    val lastError: String? = null,
)

@Entity(tableName = "cache_metadata")
data class CacheMetadataEntity(
    @PrimaryKey val key: String,
    val value: String,
    val updatedAt: Long,
)

object SyncState {
    const val PENDING = "PENDING"
    const val SYNCED = "SYNCED"
    const val FAILED = "FAILED"
}

object OperationKind {
    const val BOOK_SEATS = "BOOK_SEATS"
    const val CANCEL_BOOKING = "CANCEL_BOOKING"
    const val RATE_TRIP = "RATE_TRIP"
    const val ADVANCE_TRIP = "ADVANCE_TRIP"
    const val PING_LOCATION = "PING_LOCATION"
}

object CacheKeys {
    const val GEO_VERSION = "geo_version"
    const val GEO_SYNCED_AT = "geo_synced_at"

    /**
     * The emergency numbers, cached so the sheet needs no network.
     *
     * A key/value row rather than a table: this is one small object, read on
     * the worst day of somebody's year, and a Room migration to hold it would
     * be a schema change for four strings.
     */
    const val SAFETY_CONTACTS = "safety_contacts"
}
