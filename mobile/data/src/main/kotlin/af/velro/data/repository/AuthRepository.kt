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
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
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

    /** Sign out. What leaves the phone is [forgetThisHandset]'s to decide. */
    suspend fun signOut(allDevices: Boolean = false) {
        if (allDevices) {
            runCatching { api.logoutAllDevices() }
        }
        forgetThisHandset()
    }

    private val _accountDeleted = MutableStateFlow(false)

    /**
     * An account was deleted from this phone, and the person has not moved on.
     *
     * The sign-in screen that follows the deletion says so, until somebody
     * starts signing in again and it calls [acknowledgeAccountDeleted].
     * Without that one line the only answer to "delete my account" is the app
     * silently signing out, which reads the same as a session that expired.
     *
     * Observed rather than read once, because the screen can arrive before
     * the flag does: on a retry (see [alreadyDeleted]) it is the refused
     * refresh that clears the session, and so opens sign-in, while the answer
     * is still on its way back to [deleteAccount].
     *
     * In memory, not on disk. A process that dies in between loses the
     * sentence and nothing else -- the account is gone either way.
     */
    val accountDeleted: StateFlow<Boolean> = _accountDeleted.asStateFlow()

    fun acknowledgeAccountDeleted() {
        _accountDeleted.value = false
    }

    /**
     * Delete the account, and then everything this phone knows about it.
     *
     * The phone forgets exactly what signing out forgets -- one function does
     * both, so the two cannot come to disagree -- but never calls the logout
     * endpoint: the server has already revoked every session the account had,
     * on this phone and on any other.
     *
     * Not cancellable once asked. The server may carry the deletion out while
     * its answer is still crossing a valley, and if leaving the screen could
     * cancel the rest, this phone would go on holding the name and the
     * journeys of an account that no longer exists -- the one outcome the
     * whole feature is for. So the call and the forgetting finish together,
     * whatever the screen does in the meantime.
     *
     * A refusal changes nothing here. The account, the session and the cache
     * are exactly as they were, and the code goes back to the screen to say.
     */
    suspend fun deleteAccount(): ApiResult<Unit> = withContext(NonCancellable) {
        val result = mapper.call { api.deleteAccount() }
        if (result is ApiResult.Success || alreadyDeleted(result)) {
            _accountDeleted.value = true
            forgetThisHandset()
            ApiResult.Success(Unit)
        } else {
            result.map { }
        }
    }

    /**
     * Everything this phone holds about the person: the cache, then the session.
     *
     * Shared by signing out and by deleting the account. The cache is wiped
     * before the session is cleared, and both run off the main thread.
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
    private suspend fun forgetThisHandset() {
        withContext(Dispatchers.IO) {
            db.clearAllTables()
            tokens.clear()
        }
    }

    internal companion object {
        /**
         * The answer a retry gets when the first attempt had already worked.
         *
         * A deletion whose answer was lost on the way back leaves this phone
         * holding a session for an account the server has closed. The retry
         * is then refused the way every request from that account is --
         * USER_SUSPENDED, carrying the account's status -- and DEACTIVATED is
         * the status nothing but a deletion sets. That is the outcome that was
         * asked for. Read as a failure, the phone would be signed out by the
         * refused refresh with the account's journeys still in its cache, and
         * told nothing.
         *
         * A suspended account is SUSPENDED, and stays a refusal.
         */
        fun alreadyDeleted(result: ApiResult<*>): Boolean {
            val error = (result as? ApiResult.Failure)?.error ?: return false
            return error.code == "USER_SUSPENDED" && error.context["status"] == "DEACTIVATED"
        }
    }
}
