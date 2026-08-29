package af.velro.data.repository

import af.velro.data.api.ApiResult
import af.velro.data.api.ResponseMapper
import af.velro.data.api.VelroApi
import af.velro.data.db.CacheKeys
import af.velro.data.db.CacheMetadataEntity
import af.velro.data.db.StationDestinationEntity
import af.velro.data.db.VelroDatabase
import af.velro.domain.Destination
import af.velro.domain.DestinationGroup
import af.velro.domain.District
import af.velro.domain.Station
import af.velro.domain.Village
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

/**
 * Geography, cache-first.
 *
 * Reads always come from the local database, so browsing works with no network
 * whatsoever. The network is only used to refresh, and the refresh is a no-op
 * when the server says the version has not changed -- which it usually has not,
 * because the districts of Ghorband do not move.
 */
@Singleton
class GeographyRepository @Inject constructor(
    private val api: VelroApi,
    private val db: VelroDatabase,
    private val mapper: ResponseMapper,
) {

    fun districts(): Flow<List<District>> =
        db.geography().districts().map { rows -> rows.map { it.toDomain() } }

    fun villages(districtId: String): Flow<List<Village>> =
        db.geography().villages(districtId).map { rows -> rows.map { it.toDomain() } }

    fun stations(villageId: String): Flow<List<Station>> =
        db.geography().stations(villageId).map { rows -> rows.map { it.toDomain() } }

    suspend fun station(id: String): Station? = db.geography().station(id)?.toDomain()

    suspend fun destination(id: String): Destination? =
        db.geography().destination(id)?.toDomain()

    /** Searches the cache first; falls back to the server only if it finds nothing. */
    suspend fun search(term: String, limit: Int = 20): List<SearchHit> {
        val local = buildList {
            db.geography().searchVillages(term, limit).forEach {
                add(SearchHit.OfVillage(it.toDomain()))
            }
            db.geography().searchStations(term, limit).forEach {
                add(SearchHit.OfStation(it.toDomain()))
            }
        }
        if (local.isNotEmpty()) return local

        return when (val result = mapper.call { api.searchPlaces(term, limit) }) {
            is ApiResult.Success -> result.value.mapNotNull { hit ->
                when (hit.kind) {
                    "station" -> db.geography().station(hit.id)?.let {
                        SearchHit.OfStation(it.toDomain())
                    }
                    else -> null
                }
            }
            is ApiResult.Failure -> emptyList()
        }
    }

    /**
     * Which destinations this origin can reach.
     *
     * Cached per station, because it is the screen immediately before booking
     * and a passenger standing at a roadside should not wait for it.
     */
    suspend fun destinationsFrom(stationId: String): ApiResult<List<DestinationGroup>> {
        val cached = db.geography().destinationsFrom(stationId)
        if (cached.isNotEmpty()) {
            return ApiResult.Success(groupCached(cached))
        }
        return when (val result = mapper.call { api.destinationsFrom(stationId) }) {
            is ApiResult.Success -> {
                val groups = result.value.map { it.toDomain() }
                cacheDestinations(stationId, groups)
                ApiResult.Success(groups)
            }
            is ApiResult.Failure -> result
        }
    }

    private suspend fun cacheDestinations(stationId: String, groups: List<DestinationGroup>) {
        val flat = groups.flatMap { group ->
            buildList {
                add(
                    af.velro.data.db.DestinationEntity(
                        id = group.id, code = group.code, name = group.name, kind = group.kind,
                        parentId = null, districtId = null, stationId = null, sortOrder = 0,
                    )
                )
                group.children.forEach { child ->
                    add(
                        af.velro.data.db.DestinationEntity(
                            id = child.id, code = child.code, name = child.name,
                            kind = child.kind, parentId = group.id, districtId = null,
                            stationId = null, sortOrder = child.sortOrder,
                        )
                    )
                }
            }
        }
        db.geography().upsertDestinations(flat)
        db.geography().clearDestinationsFor(stationId)
        db.geography().upsertStationDestinations(
            flat.map { StationDestinationEntity(stationId, it.id) }
        )
    }

    private fun groupCached(rows: List<af.velro.data.db.DestinationEntity>): List<DestinationGroup> {
        val byParent = rows.groupBy { it.parentId }
        return byParent[null].orEmpty().map { parent ->
            DestinationGroup(
                id = parent.id, code = parent.code, name = parent.name, kind = parent.kind,
                children = byParent[parent.id].orEmpty()
                    .map { it.toDomain() }
                    .sortedBy { it.sortOrder },
            )
        }.sortedBy { it.name }
    }

    /**
     * Refresh the whole hierarchy, or confirm it is already current.
     *
     * Sends the cached version; a 304 means nothing to download. On a 2G
     * connection this is the difference between a usable app and one that
     * spends a minute on a splash screen.
     */
    suspend fun refresh(): ApiResult<Boolean> {
        val known = db.cacheMetadata().get(CacheKeys.GEO_VERSION)
        val response = try {
            api.geoSnapshot(known)
        } catch (e: java.io.IOException) {
            return ApiResult.Failure(af.velro.data.api.ApiException.offline())
        } catch (e: Exception) {
            // Reached the server but could not read the answer.
            return ApiResult.Failure(
                af.velro.data.api.ApiException(
                    code = af.velro.data.api.ApiException.UNKNOWN,
                    httpStatus = 0,
                    context = mapOf("reason" to "response_unreadable"),
                )
            )
        }

        if (response.code() == 304) return ApiResult.Success(false)

        return when (val result = mapper.unwrap(response)) {
            is ApiResult.Success -> {
                val snapshot = result.value
                db.geography().replaceSnapshot(
                    districts = snapshot.districts.map { it.toEntity() },
                    villages = snapshot.villages.map { it.toEntity() },
                    stations = snapshot.stations.map { it.toEntity() },
                    destinations = snapshot.destinations.map { it.toEntity() },
                )
                db.cacheMetadata().put(
                    CacheMetadataEntity(
                        key = CacheKeys.GEO_VERSION,
                        value = snapshot.version,
                        updatedAt = System.currentTimeMillis(),
                    )
                )
                ApiResult.Success(true)
            }
            is ApiResult.Failure -> result
        }
    }

    suspend fun nearby(latitude: Double, longitude: Double, radiusMetres: Int = 15_000):
        ApiResult<List<Station>> =
        mapper.call {
            api.nearbyStations(latitude.toString(), longitude.toString(), radiusMetres)
        }.map { list -> list.map { it.toDomain() } }

    suspend fun isCached(): Boolean = db.cacheMetadata().get(CacheKeys.GEO_VERSION) != null
}

sealed interface SearchHit {
    data class OfVillage(val village: Village) : SearchHit
    data class OfStation(val station: Station) : SearchHit
}
