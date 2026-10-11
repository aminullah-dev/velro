package af.velro.passenger.onboarding

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.onboardingStore by preferencesDataStore(name = "velro_onboarding")

/**
 * Whether this handset has been shown the three onboarding pages.
 *
 * Its own store, not a key in the session's: signing out wipes the session
 * and the cache -- a shared phone is the ordinary case -- and the next person
 * on it has no more need of "name your fare" explained than the last one did.
 * What the pages teach is about the product, not about an account, so it
 * belongs to the handset.
 *
 * DataStore, like every other preference in the app, so the first read is
 * off the main thread and the caller waits for it rather than guessing.
 */
@Singleton
class OnboardingStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private val seenKey = booleanPreferencesKey("seen")

    val seen: Flow<Boolean> = context.onboardingStore.data.map { it[seenKey] ?: false }

    suspend fun markSeen() {
        context.onboardingStore.edit { it[seenKey] = true }
    }
}
