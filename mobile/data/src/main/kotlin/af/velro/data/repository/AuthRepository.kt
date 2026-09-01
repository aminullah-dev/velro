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
import af.velro.domain.UserProfile
import af.velro.data.api.ProfileDto
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

    suspend fun profile(): ApiResult<UserProfile> =
        mapper.call { api.profile() }.map(::toDomain)

    /**
     * Change the name the driver will see.
     *
     * The phone is not editable here: it is the account, not a field on it.
     */
    suspend fun updateName(fullName: String?): ApiResult<UserProfile> =
        mapper.call { api.updateProfile(UpdateProfileRequest(full_name = fullName)) }
            .map(::toDomain)

    /**
     * Change the language, after sign-in.
     *
     * The picker existed only on the sign-in screen, and the choice is stored
     * and then drives the whole app -- so somebody who tapped the wrong one, or
     * whose handset was set up by a relative, was locked into a language they
     * could not read, with the way out labelled in it.
     *
     * Written locally first because that is what the app actually reads. The
     * server is told so the next SMS arrives in the right language; if that
     * call fails the app is already correct and the account catches up on the
     * next successful write.
     */
    suspend fun changeLocale(locale: Locale) {
        tokens.saveLocale(locale.tag)
        runCatching { api.updateProfile(UpdateProfileRequest(locale = locale.tag)) }
    }

    private fun toDomain(dto: ProfileDto) = UserProfile(
        id = dto.id,
        phone = dto.phone,
        fullName = dto.full_name,
        locale = Locale.fromTag(dto.locale),
        completedTrips = dto.completed_trips,
        memberSince = dto.member_since,
        ratingAverage = dto.rating_average,
        ratingCount = dto.rating_count,
    )

    suspend fun requestOtp(
        phone: String,
        locale: Locale,
        /** Where the person asked for it: "sms" or "telegram". */
        channel: String = "sms",
    ): ApiResult<RequestOtpResponse> =
        mapper.call { api.requestOtp(RequestOtpRequest(phone, locale.tag, channel)) }

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
