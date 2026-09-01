package af.velro.data

import af.velro.data.api.SessionDto
import af.velro.data.api.SessionTokens
import af.velro.data.api.TokenRefreshAuthenticator
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * What happens when a whole screen's worth of requests expires at once.
 *
 * Refresh tokens rotate and the server treats a replay as theft: it revokes
 * every session the user has. So a second refresh is not a wasted call, it
 * is a driver signed out of the phone he is working from, in a valley,
 * with no way back but an SMS. This is the test that says only one goes.
 */
class TokenRefreshRaceTest {

    private class FakeTokens : SessionTokens {
        @Volatile var access: String? = "old-access"
        @Volatile var refresh: String? = "refresh-1"
        val cleared = AtomicInteger()

        override suspend fun currentAccessToken(): String? = access
        override suspend fun currentRefreshToken(): String? = refresh
        override suspend fun deviceId(): String = "test-device"
        override suspend fun save(session: SessionDto) {
            access = session.access_token
            refresh = session.refresh_token
        }
        override suspend fun clear() {
            cleared.incrementAndGet()
            access = null
            refresh = null
        }
    }

    private fun unauthorized(withToken: String) = Response.Builder()
        .request(
            Request.Builder()
                .url("http://localhost/api/v1/driver/trips/current")
                .header("Authorization", "Bearer $withToken")
                .build()
        )
        .protocol(Protocol.HTTP_1_1)
        .code(401)
        .message("Unauthorized")
        .body("".toResponseBody(null))
        .build()

    private fun sessionResponse(access: String, refresh: String) = Response.Builder()
        .request(Request.Builder().url("http://localhost/api/v1/auth/refresh").build())
        .protocol(Protocol.HTTP_1_1)
        .code(200)
        .message("OK")
        .body(
            """{"success":true,"data":{"user_id":"u","access_token":"$access",
               "refresh_token":"$refresh","roles":["DRIVER"],"is_new_user":false,
               "expires_in_seconds":900}}""".trimIndent()
                .toResponseBody("application/json".toMediaType())
        )
        .build()

    @Test
    fun `eight requests expiring together spend exactly one refresh`() {
        val tokens = FakeTokens()
        val refreshes = AtomicInteger()
        val authenticator = TokenRefreshAuthenticator(
            tokens, Json { ignoreUnknownKeys = true },
        ) { presented, _ ->
            // The server's own rule, modelled: a rotated token used twice is
            // theft, and the whole session dies.
            val n = refreshes.incrementAndGet()
            if (presented != "refresh-1") {
                throw AssertionError("a replayed refresh token reached the server")
            }
            sessionResponse("new-access", "refresh-$n-rotated")
        }

        val threads = 8
        val pool = Executors.newFixedThreadPool(threads)
        val start = CountDownLatch(1)
        val done = CountDownLatch(threads)
        val retried = java.util.Collections.synchronizedList(mutableListOf<String?>())

        repeat(threads) {
            pool.execute {
                start.await()
                val request = authenticator.authenticate(null, unauthorized("old-access"))
                retried.add(request?.header("Authorization"))
                done.countDown()
            }
        }
        start.countDown()
        check(done.await(10, TimeUnit.SECONDS)) { "authenticate deadlocked" }
        pool.shutdown()

        assertEquals("only one refresh may be spent", 1, refreshes.get())
        assertEquals("every caller retries with the renewed token",
            List(threads) { "Bearer new-access" }, retried.toList())
        assertEquals("the session must not be cleared", 0, tokens.cleared.get())
    }

    @Test
    fun `a request that never carried a token is not refreshed for`() {
        val tokens = FakeTokens()
        val authenticator = TokenRefreshAuthenticator(tokens, Json {}) { _, _ ->
            throw AssertionError("must not refresh")
        }
        val anonymous = Response.Builder()
            .request(Request.Builder().url("http://localhost/api/v1/auth/otp/request").build())
            .protocol(Protocol.HTTP_1_1).code(401).message("Unauthorized")
            .body("".toResponseBody(null)).build()
        assertEquals(null, authenticator.authenticate(null, anonymous))
    }
}
