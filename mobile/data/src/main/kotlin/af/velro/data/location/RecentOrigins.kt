package af.velro.data.location

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.Serializable
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json

private val Context.recentOriginsStore by preferencesDataStore(name = "velro_recent_origins")

/**
 * Where this passenger has asked from before, newest first.
 *
 * On the phone and nowhere else. The server keeps a place's name without its
 * people (ADR 0015); the one list that says "she asked from here" lives on her
 * own handset, is five rows long, and is wiped with everything else when she
 * signs out -- a shared phone is the ordinary case.
 *
 * A PENDING name she typed lives here too: the server shows it to nobody else
 * until staff have read it, but it is hers, and she should not have to type
 * it again tomorrow.
 */
@Singleton
class RecentOrigins @Inject constructor(
    @ApplicationContext private val context: Context,
) {

    @Serializable
    data class Entry(
        val stationId: String,
        val stationName: String,
        val districtId: String,
        val placeId: String? = null,
        val placeName: String? = null,
        val usedAt: Long = 0L,
    )

    private val key = stringPreferencesKey("entries")
    private val json = Json { ignoreUnknownKeys = true }
    private val serializer = ListSerializer(Entry.serializer())

    val entries: Flow<List<Entry>> = context.recentOriginsStore.data.map { prefs ->
        prefs[key]?.let { runCatching { json.decodeFromString(serializer, it) }.getOrNull() }
            .orEmpty()
    }

    /** Puts this origin first, drops any older copy of it, keeps [LIMIT]. */
    suspend fun remember(entry: Entry) {
        context.recentOriginsStore.edit { prefs ->
            val current = prefs[key]
                ?.let { runCatching { json.decodeFromString(serializer, it) }.getOrNull() }
                .orEmpty()
            prefs[key] = json.encodeToString(serializer, merged(current, entry))
        }
    }

    suspend fun clear() {
        context.recentOriginsStore.edit { it.remove(key) }
    }

    companion object {
        const val LIMIT = 5

        /**
         * The list after [entry] is used. Pure, so the ordering rules are tested
         * without a DataStore: newest first, one row per station-and-place.
         */
        fun merged(current: List<Entry>, entry: Entry): List<Entry> =
            (listOf(entry) + current.filterNot {
                it.stationId == entry.stationId && it.placeId == entry.placeId
            }).take(LIMIT)
    }
}
