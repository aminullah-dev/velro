package af.velro.data.api

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

        val refreshed: SessionDto? = runBlocking {
            runCatching {
                val deviceId = tokens.deviceId()
                val raw = refreshCall(refreshToken, deviceId)
                if (!raw.isSuccessful) {
                    tokens.clear()
                    return@runCatching null
                }
                val body = raw.body?.string() ?: return@runCatching null
                json.decodeFromString<Envelope<SessionDto>>(body).data
            }.getOrNull()
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

    /** A fresh attempt id, held by the screen so a rotation does not change it. */
    fun newAttemptId(): String = UUID.randomUUID().toString()
}
