package af.velro.data

import af.velro.data.api.ApiResult
import af.velro.data.api.Envelope
import af.velro.data.api.ResponseMapper
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Response

/**
 * `data: null` as an answer, not as a failure.
 *
 * Two endpoints document a null payload as a real reply: `driver/trips/current`
 * says "no trip right now" and `driver/vehicles/current` says "no vehicle
 * registered". [ResponseMapper.call] cannot tell that apart from a server that
 * dropped an object it owed, because a null is a null once the type is erased,
 * so it takes the safe reading and fails.
 *
 * That reading cost the driver's home screen. The screen counts failures across
 * its five reads and sets isStale from the count, and isStale draws "You are
 * offline. Showing saved data." So a driver with no assignment -- which is
 * exactly a driver who is free to take work -- was told he had no connection,
 * on a screen whose other four reads had just succeeded over that connection.
 *
 * These hold the distinction: nullable where it is documented, strict
 * everywhere else.
 */
class NullPayloadTest {

    private val mapper = ResponseMapper(Json { ignoreUnknownKeys = true })

    private fun <T> ok(data: T) = Response.success(Envelope(data = data))

    private fun <T> httpError(code: Int): Response<Envelope<T>> =
        Response.error(code, """{"success":false}""".toResponseBody("application/json".toMediaType()))

    @Test
    fun `a null payload is an answer when the caller asked for one`() = runTest {
        val result = mapper.callNullable { ok<String?>(null) }
        assertTrue("a documented null must not be a failure", result is ApiResult.Success)
        assertNull((result as ApiResult.Success).value)
    }

    @Test
    fun `a value still arrives intact through the nullable path`() = runTest {
        val result = mapper.callNullable { ok<String?>("trip") }
        assertEquals("trip", (result as ApiResult.Success).value)
    }

    @Test
    fun `the nullable path still fails on a real HTTP error`() = runTest {
        // The point of keeping this opt-in: a 500 with an empty body must not
        // become a cheerful "there is no trip".
        val result = mapper.callNullable { httpError<String?>(500) }
        assertTrue(result is ApiResult.Failure)
    }

    @Test
    fun `the strict path still refuses a null it did not expect`() = runTest {
        // An endpoint that owes an object and sends null is a fault, and
        // loosening call() for everyone would have hidden it.
        val result = mapper.call { ok<String?>(null) }
        assertTrue("call() must stay strict", result is ApiResult.Failure)
    }
}
