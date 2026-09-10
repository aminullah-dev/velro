package af.velro.data.api

import java.io.IOException
import java.util.UUID
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import okhttp3.Authenticator
import okhttp3.Interceptor
import okhttp3.Request
import okhttp3.Response
import okhttp3.Route

/** Attaches the access token and a request id to every call. */
class AuthInterceptor(private val tokens: SessionTokens) : Interceptor {

    override fun intercept(chain: Interceptor.Chain): Response {
        val token = runBlocking { tokens.currentAccessToken() }
        val builder: Request.Builder = chain.request().newBuilder()
            // Generated client-side so a request can be traced end to end even
            // when the response never arrives.
            .header("X-Request-ID", UUID.randomUUID().toString())
        if (token != null) {
            builder.header("Authorization", "Bearer $token")
        }
        return chain.proceed(builder.build())
    }
}

/**
 * Refreshes an expired access token once, then replays the request.
 *
 * OkHttp calls this only on a 401, and only once per request, so a refresh that
 * itself fails cannot loop. A refresh token that the server has revoked means
 * the session is genuinely over: the local session is cleared and the app
 * returns to sign-in rather than retrying forever.
 */
class TokenRefreshAuthenticator(
    private val tokens: SessionTokens,
    private val json: Json,
    private val refreshCall: suspend (String, String?) -> Response,
) : Authenticator {

    /**
     * Renew the session, exactly once no matter how many calls expire at once.
     *
     * Refresh tokens rotate, and the server treats a replayed one as theft:
     * it revokes every session that user has (RefreshSession). Two requests
     * expiring together -- which is the normal case, since everything on a
     * screen expires in the same second -- would each post the same refresh
     * token, and the loser's replay would sign the driver out of a phone he
     * is working from. Hence the lock, and the check after it: whoever waits
     * finds the token already renewed and simply retries with it, spending
     * no second refresh at all.
     */
    @Synchronized
    override fun authenticate(route: Route?, response: Response): Request? {
        val used = response.request.header("Authorization") ?: return null
        if (priorResponseCount(response) >= 1) return null   // already retried once

        val current = runBlocking { tokens.currentAccessToken() }
        if (current != null && "Bearer $current" != used) {
            // Renewed by whoever held the lock first. Nothing to do but use it.
            return response.request.newBuilder()
                .header("Authorization", "Bearer $current")
                .build()
        }

        val refreshToken = runBlocking { tokens.currentRefreshToken() } ?: return null

        val raw = try {
            runBlocking { refreshCall(refreshToken, tokens.deviceId()) }
        } catch (e: IOException) {
            // Only the server can end a session. A refresh that never reached
            // it -- the valley with no signal, which is where tokens expire --
            // used to land in the same branch as a revoked token and clear the
            // session, signing the passenger out of an app she could not sign
            // back into without the connection she did not have. The session
            // is kept, and the call fails as a call does offline: the caller
            // sees NETWORK_OFFLINE, and the next request, with signal, renews.
            throw IOException("session renewal could not reach the server", e)
        }

        val refreshed: SessionDto? = raw.use {
            when {
                // Server trouble or a rate limit is not a verdict on the session.
                it.code == 429 || it.code >= 500 ->
                    throw IOException("session renewal refused for now (HTTP ${it.code})")
                // A refusal -- revoked, expired, replayed -- is the end of it.
                !it.isSuccessful -> null
                else -> runCatching {
                    json.decodeFromString<Envelope<SessionDto>>(it.body?.string().orEmpty()).data
                }.getOrNull()
                    // A 2xx nobody can read is a contract fault, not a refusal.
                    ?: throw IOException("session renewal answer could not be read")
            }
        }

        if (refreshed == null) {
            runBlocking { tokens.clear() }
            return null
        }
        runBlocking { tokens.save(refreshed) }

        return response.request.newBuilder()
            .header("Authorization", "Bearer ${refreshed.access_token}")
            .build()
    }

    private fun priorResponseCount(response: Response): Int {
        var count = 0
        var prior = response.priorResponse
        while (prior != null) {
            count++
            prior = prior.priorResponse
        }
        return count
    }
}

/**
 * A client-generated key for every mutation.
 *
 * Derived from the operation and its inputs rather than random, so a retry of
 * *the same* action reuses the key and the server returns the original
 * response, while a genuinely new action gets a new one.
 */
object IdempotencyKeys {
    fun forBooking(tripId: String, seatCount: Int, stationId: String, attemptId: String): String =
        "booking:$tripId:$seatCount:$stationId:$attemptId"

    fun forAccept(tripId: String, driverId: String): String = "accept:$tripId:$driverId"

    /**
     * One accept per attempt, bound to the offer it was for.
     *
     * The offer id alone is not a key: it is printed on the driver's own
     * screen, and a key another account can name is a key another account can
     * try. The server refuses that regardless -- a stored answer only ever
     * opens for the account that earned it -- but the attempt id keeps the key
     * private from this end too, exactly as an ask's and a booking's are.
     */
    fun forAcceptOffer(offerId: String, attemptId: String): String =
        "accept_offer:$offerId:$attemptId"

    /** One ask per attempt: the same journey, seats and attempt id replay as one request. */
    fun forAsk(originStationId: String, destinationId: String, seats: Int, attemptId: String): String =
        "ask:$originStationId:$destinationId:$seats:$attemptId"

    /** A fresh attempt id, held by the screen so a rotation does not change it. */
    fun newAttemptId(): String = UUID.randomUUID().toString()
}
