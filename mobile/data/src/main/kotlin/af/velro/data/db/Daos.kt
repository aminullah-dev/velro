package af.velro.data.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import androidx.room.Upsert
import kotlinx.coroutines.flow.Flow

@Dao
interface GeographyDao {

    @Query("SELECT * FROM districts ORDER BY code")
    fun districts(): Flow<List<DistrictEntity>>

    @Query("SELECT * FROM villages WHERE districtId = :districtId ORDER BY name")
    fun villages(districtId: String): Flow<List<VillageEntity>>

    @Query("SELECT * FROM stations WHERE villageId = :villageId ORDER BY isPrimary DESC, name")
    fun stations(villageId: String): Flow<List<StationEntity>>

    @Query("SELECT * FROM stations WHERE id = :id")
    suspend fun station(id: String): StationEntity?

    /**
     * Offline search over the cached names.
     *
     * A LIKE scan is fine here: the whole of Ghorband is a few thousand rows,
     * and this must work with no network at all.
     */
    @Query(
        """
        SELECT * FROM villages
        WHERE name LIKE '%' || :term || '%' OR code LIKE '%' || :term || '%'
        ORDER BY length(name) LIMIT :limit
        """
    )
    suspend fun searchVillages(term: String, limit: Int = 20): List<VillageEntity>

    @Query(
        """
        SELECT * FROM stations
        WHERE name LIKE '%' || :term || '%'
        ORDER BY length(name) LIMIT :limit
        """
    )
    suspend fun searchStations(term: String, limit: Int = 20): List<StationEntity>

    @Query(
        """
        SELECT d.* FROM destinations d
        JOIN station_destinations sd ON sd.destinationId = d.id
        WHERE sd.stationId = :stationId
        ORDER BY d.sortOrder, d.name
        """
    )
    suspend fun destinationsFrom(stationId: String): List<DestinationEntity>

    @Query("SELECT * FROM destinations WHERE id = :id")
    suspend fun destination(id: String): DestinationEntity?

    @Query("SELECT * FROM destinations ORDER BY sortOrder, name")
    suspend fun allDestinations(): List<DestinationEntity>

    @Upsert suspend fun upsertDistricts(rows: List<DistrictEntity>)
    @Upsert suspend fun upsertVillages(rows: List<VillageEntity>)
    @Upsert suspend fun upsertStations(rows: List<StationEntity>)
    @Upsert suspend fun upsertDestinations(rows: List<DestinationEntity>)

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsertStationDestinations(rows: List<StationDestinationEntity>)

    @Query("DELETE FROM station_destinations WHERE stationId = :stationId")
    suspend fun clearDestinationsFor(stationId: String)

    /**
     * Replaces the whole hierarchy in one transaction.
     *
     * Half a snapshot is worse than none: a partially applied update would show
     * villages whose stations are missing.
     */
    @Transaction
    suspend fun replaceSnapshot(
        districts: List<DistrictEntity>,
        villages: List<VillageEntity>,
        stations: List<StationEntity>,
        destinations: List<DestinationEntity>,
    ) {
        upsertDistricts(districts)
        upsertVillages(villages)
        upsertStations(stations)
        upsertDestinations(destinations)
    }
}

@Dao
interface BookingDao {

    @Query("SELECT * FROM bookings ORDER BY createdAt DESC LIMIT :limit")
    fun recent(limit: Int = 20): Flow<List<BookingEntity>>

    @Query("SELECT * FROM bookings WHERE id = :id")
    fun booking(id: String): Flow<BookingEntity?>

    @Query("SELECT * FROM bookings WHERE status IN (:statuses) ORDER BY createdAt DESC")
    fun active(statuses: List<String>): Flow<List<BookingEntity>>

    /**
     * What the history screen shows with no signal.
     *
     * Ordered like the server's own list -- newest first, tie-broken on id --
     * so the cached view and the fresh one are not in a different order.
     */
    @Query(
        "SELECT * FROM bookings WHERE status IN (:statuses) " +
            "ORDER BY createdAt DESC, id DESC LIMIT :limit"
    )
    suspend fun cachedByStatus(statuses: List<String>, limit: Int): List<BookingEntity>

    @Upsert suspend fun upsert(booking: BookingEntity)
    @Upsert suspend fun upsertAll(bookings: List<BookingEntity>)

    @Query("DELETE FROM bookings WHERE id = :id")
    suspend fun delete(id: String)
}

@Dao
interface TripDao {
    @Query("SELECT * FROM trips WHERE id = :id")
    fun trip(id: String): Flow<TripEntity?>

    @Upsert suspend fun upsert(trip: TripEntity)
}

@Dao
interface PendingOperationDao {

    @Query("SELECT * FROM pending_operations ORDER BY createdAt")
    suspend fun all(): List<PendingOperationEntity>

    @Query("SELECT COUNT(*) FROM pending_operations")
    fun count(): Flow<Int>

    @Upsert suspend fun upsert(operation: PendingOperationEntity)

    @Query("DELETE FROM pending_operations WHERE id = :id")
    suspend fun delete(id: String)

    @Query("UPDATE pending_operations SET attempts = attempts + 1, lastError = :error WHERE id = :id")
    suspend fun recordFailure(id: String, error: String)
}

@Dao
interface CacheMetadataDao {
    @Query("SELECT value FROM cache_metadata WHERE key = :key")
    suspend fun get(key: String): String?

    @Upsert suspend fun put(row: CacheMetadataEntity)
}
