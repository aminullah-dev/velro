package af.velro.data.db

import androidx.room.Database
import androidx.room.RoomDatabase

/**
 * The local database.
 *
 * Migration tests are mandatory for this class: an unmigrated database on a
 * driver's phone in Ghorband is unrecoverable remotely, and the only fix would
 * be asking them to reinstall and lose their offline queue.
 */
@Database(
    entities = [
        DistrictEntity::class,
        VillageEntity::class,
        StationEntity::class,
        DestinationEntity::class,
        StationDestinationEntity::class,
        BookingEntity::class,
        TripEntity::class,
        PendingOperationEntity::class,
        CacheMetadataEntity::class,
    ],
    version = 1,
    exportSchema = true,
)
abstract class VelroDatabase : RoomDatabase() {
    abstract fun geography(): GeographyDao
    abstract fun bookings(): BookingDao
    abstract fun trips(): TripDao
    abstract fun pendingOperations(): PendingOperationDao
    abstract fun cacheMetadata(): CacheMetadataDao

    companion object {
        const val NAME = "velro.db"
    }
}
