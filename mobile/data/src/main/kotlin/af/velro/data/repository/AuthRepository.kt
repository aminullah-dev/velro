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
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

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
     * Clears the local session first so the app never appears signed in after
     * the person tapped sign out, then tells the server. Wiping the cache too:
     * a shared handset is common, and the next person must not see the last
     * one's bookings.
     */
    suspend fun signOut(allDevices: Boolean = false) {
        if (allDevices) {
            runCatching { api.logoutAllDevices() }
        }
        tokens.clear()
        db.clearAllTables()
    }
}
