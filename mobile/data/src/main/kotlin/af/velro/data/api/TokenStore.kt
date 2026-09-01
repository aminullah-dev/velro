package af.velro.data.api

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import java.util.UUID
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map

private val Context.tokenDataStore by preferencesDataStore(name = "velro_session")

/**
 * The part of the session store the network layer touches.
 *
 * Extracted so the refresh authenticator can be exercised without Android:
 * the thing worth testing about it is what happens when several expired
 * requests race, and that must not need a device to find out.
 */
interface SessionTokens {
    suspend fun currentAccessToken(): String?
    suspend fun currentRefreshToken(): String?
    suspend fun deviceId(): String
    suspend fun save(session: SessionDto)
    suspend fun clear()
}

/**
 * Where the session lives on the device.
 *
 * DataStore rather than SharedPreferences: the reads are on the request path
 * and must not block the main thread. The device id is generated once and kept,
 * so "sign out of all devices" can distinguish this handset from the others.
 */
class TokenStore(private val context: Context) : SessionTokens {

    private object Keys {
        val access = stringPreferencesKey("access_token")
        val refresh = stringPreferencesKey("refresh_token")
        val userId = stringPreferencesKey("user_id")
        val roles = stringPreferencesKey("roles")
        val locale = stringPreferencesKey("locale")
        val deviceId = stringPreferencesKey("device_id")
    }

    val accessToken: Flow<String?> =
        context.tokenDataStore.data.map { it[Keys.access] }

    val isSignedIn: Flow<Boolean> =
        context.tokenDataStore.data.map { it[Keys.access] != null }

    val userId: Flow<String?> = context.tokenDataStore.data.map { it[Keys.userId] }

    val roles: Flow<List<String>> = context.tokenDataStore.data.map {
        it[Keys.roles]?.split(",")?.filter(String::isNotBlank).orEmpty()
    }

    val locale: Flow<String> =
        context.tokenDataStore.data.map { it[Keys.locale] ?: "fa-AF" }

    override suspend fun currentAccessToken(): String? =
        context.tokenDataStore.data.first()[Keys.access]

    override suspend fun currentRefreshToken(): String? =
        context.tokenDataStore.data.first()[Keys.refresh]

    override suspend fun deviceId(): String {
        val existing = context.tokenDataStore.data.first()[Keys.deviceId]
        if (existing != null) return existing
        val generated = UUID.randomUUID().toString()
        context.tokenDataStore.edit { it[Keys.deviceId] = generated }
        return generated
    }

    override suspend fun save(session: SessionDto) {
        context.tokenDataStore.edit {
            it[Keys.access] = session.access_token
            it[Keys.refresh] = session.refresh_token
            it[Keys.userId] = session.user_id
            it[Keys.roles] = session.roles.joinToString(",")
        }
    }

    suspend fun saveLocale(tag: String) {
        context.tokenDataStore.edit { it[Keys.locale] = tag }
    }

    /** Clears the session but keeps the device id and the chosen language. */
    override suspend fun clear() {
        context.tokenDataStore.edit {
            it.remove(Keys.access)
            it.remove(Keys.refresh)
            it.remove(Keys.userId)
            it.remove(Keys.roles)
        }
    }
}
