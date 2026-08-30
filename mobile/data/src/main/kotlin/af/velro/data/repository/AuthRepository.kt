package af.velro.data.repository

import af.velro.data.api.ApiResult
import af.velro.data.api.RequestOtpRequest
import af.velro.data.api.RequestOtpResponse
import af.velro.data.api.ResponseMapper
import af.velro.data.api.TokenStore
import af.velro.data.api.UpdateProfileRequest
import af.velro.data.api.VelroApi
import af.velro.data.api.VerifyOtpRequest
import af.velro.data.db.VelroDatabase
import af.velro.domain.Locale
import af.velro.domain.Session
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.withContext

@Singleton
class AuthRepository @Inject constructor(
    private val api: VelroApi,
    private val tokens: TokenStore,
    private val db: VelroDatabase,
    private val mapper: ResponseMapper,
) {

    val isSignedIn: Flow<Boolean> = tokens.isSignedIn
    val roles: Flow<List<String>> = tokens.roles
    val locale: Flow<Locale> = tokens.locale.map(Locale::fromTag)

    suspend fun requestOtp(phone: String, locale: Locale): ApiResult<RequestOtpResponse> =
        mapper.call { api.requestOtp(RequestOtpRequest(phone, locale.tag)) }

    suspend fun verifyOtp(phone: String, code: String, locale: Locale): ApiResult<Session> {
        val result = mapper.call {
            api.verifyOtp(
                VerifyOtpRequest(
                    phone = phone,
                    code = code,
                    device_id = tokens.deviceId(),
                    locale = locale.tag,
                )
            )
        }
        if (result is ApiResult.Success) {
            tokens.save(result.value)
            tokens.saveLocale(locale.tag)
        }
        return result.map { it.toDomain() }
    }

    suspend fun setLocale(locale: Locale) {
        tokens.saveLocale(locale.tag)
        // Best-effort: the server keeps a copy so notifications arrive in the
        // right language, but the local choice takes effect regardless.
        runCatching { api.updateProfile(UpdateProfileRequest(locale = locale.tag)) }
    }

    /**
     * Sign out.
     *
     * The cache is wiped before the session is cleared, and both run off the
     * main thread.
     *
     * Both of those are repairs for the same crash. `clearAllTables` is Room's
     * one blocking call -- every other access here is a suspend DAO, which Room
     * moves off the main thread itself -- and the caller is a
     * `rememberCoroutineScope` in MainActivity, which is the main thread. So
     * tapping sign out threw IllegalStateException and killed the app, in both
     * apps, every time.
     *
     * It threw between the two lines: after the session was cleared and before
     * the cache was, which is exactly the state this function exists to
     * prevent. The handset was left signed out with the previous person's
     * journeys still on it, and a shared handset is the normal case here. So
     * the cache goes first: if anything fails now, the worst outcome is an app
     * that still looks signed in, which is a confusion rather than a leak.
     */
    suspend fun signOut(allDevices: Boolean = false) {
        if (allDevices) {
            runCatching { api.logoutAllDevices() }
        }
        withContext(Dispatchers.IO) {
            db.clearAllTables()
            tokens.clear()
        }
    }
}
