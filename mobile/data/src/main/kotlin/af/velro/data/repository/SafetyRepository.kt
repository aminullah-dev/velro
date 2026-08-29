package af.velro.data.repository

import af.velro.data.api.ApiResult
import af.velro.data.api.RaiseTicketRequest
import af.velro.data.api.ResponseMapper
import af.velro.data.api.SafetyContactsDto
import af.velro.data.api.VelroApi
import af.velro.data.db.CacheKeys
import af.velro.data.db.CacheMetadataEntity
import af.velro.data.db.VelroDatabase
import af.velro.domain.SafetyContacts
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.serialization.json.Json

/**
 * The numbers to dial, and the report nobody may read until morning.
 *
 * The ordering of the two matters. Dialling must work on a handset that has
 * never once reached the server, in a valley, on a flat battery -- so the
 * numbers are compiled into the app AND refreshed from the server whenever
 * there happens to be a connection. `contacts()` never fails and never blocks
 * on the network: it answers from the cache, then the built-in default, and
 * only reaches out afterwards.
 *
 * Asking the server for an emergency number at the moment somebody needs one is
 * exactly the wrong time to ask.
 */
@Singleton
class SafetyRepository @Inject constructor(
    private val api: VelroApi,
    private val mapper: ResponseMapper,
    private val db: VelroDatabase,
) {

    /**
     * What to dial, right now, whatever the network is doing.
     *
     * Never suspends on a request. The refresh is a separate call the caller
     * makes when it is convenient, not when it is urgent.
     */
    suspend fun contacts(): SafetyContacts {
        val cached = runCatching { db.cacheMetadata().get(CacheKeys.SAFETY_CONTACTS) }
            .getOrNull()
        val parsed = cached?.let {
            runCatching {
                json.decodeFromString(SafetyContactsDto.serializer(), it).toDomain()
            }.getOrNull()
        }
        // Filtered on shape here too, not only on the server.
        //
        // A cached copy with nothing dialable in it is worse than the default:
        // it renders a sheet whose buttons open a dialler with nothing in it,
        // and it does so for as long as the row survives -- across restarts,
        // through every later offline stretch. The compiled-in numbers exist
        // precisely so there is always something behind a bad one.
        val usable = parsed?.copy(
            emergencyNumbers = parsed.emergencyNumbers.filter(::isShortDialable),
        )
        return usable?.takeIf { it.emergencyNumbers.isNotEmpty() } ?: SafetyContacts.BUILT_IN
    }

    /**
     * Refresh from the server, best effort.
     *
     * Called when a screen opens with a connection to hand. A failure is not
     * reported anywhere: the app already has numbers, and telling someone their
     * emergency numbers could not be refreshed would be alarming and useless.
     */
    suspend fun refreshContacts() {
        val result = mapper.call { api.safetyContacts() }
        if (result !is ApiResult.Success) return
        val fetched = result.value
        if (fetched.emergency_numbers.none(::isShortDialable)) return
        runCatching {
            db.cacheMetadata().put(
                CacheMetadataEntity(
                    key = CacheKeys.SAFETY_CONTACTS,
                    // The DTO is what is stored, so a cached copy written by an
                    // older build still parses.
                    value = json.encodeToString(SafetyContactsDto.serializer(), fetched),
                    updatedAt = Instant.now().toEpochMilli(),
                )
            )
        }
    }

    /** Needs a connection, and the screen says so before it is pressed. */
    suspend fun report(
        categoryCode: String,
        body: String,
        tripId: String? = null,
        bookingId: String? = null,
    ): ApiResult<String> =
        mapper.call {
            api.raiseTicket(RaiseTicketRequest(categoryCode, "", body, tripId, bookingId))
        }.map { it.reference }

    private companion object {
        /**
         * An emergency number: 3-15 ASCII digits, optional leading plus.
         *
         * Same rule as the server's _is_short_dialable. Applied on both sides
         * because either can be the one that is out of date.
         */
        fun isShortDialable(number: String): Boolean {
            val candidate = number.trim().removePrefix("+")
            return candidate.length in 3..15 && candidate.all { it in '0'..'9' }
        }

        val json = Json { ignoreUnknownKeys = true }
    }
}
