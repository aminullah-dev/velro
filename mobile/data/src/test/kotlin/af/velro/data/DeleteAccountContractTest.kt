package af.velro.data

import af.velro.data.api.ApiResult
import af.velro.data.api.ResponseMapper
import af.velro.data.api.VelroApi
import af.velro.data.repository.AuthRepository
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.io.File
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.Retrofit

/**
 * `DELETE auth/me`, from the Retrofit declaration to the code a screen reads.
 *
 * Through the real interface and the real converter rather than a hand-built
 * Response, because the seam is what can be wrong: a verb, a path resolved
 * against the base the wrong way, an envelope that does not decode. The server
 * is an interceptor that answers in-process, so nothing here opens a socket.
 */
class DeleteAccountContractTest {

    // The app's own configuration, so a lenient test cannot pass a payload
    // the app would refuse.
    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    }
    private val mapper = ResponseMapper(json)

    private fun answering(
        code: Int,
        body: String,
        seen: MutableList<Request> = mutableListOf(),
    ): VelroApi {
        val client = OkHttpClient.Builder()
            .addInterceptor { chain ->
                seen += chain.request()
                Response.Builder()
                    .request(chain.request())
                    .protocol(Protocol.HTTP_1_1)
                    .code(code)
                    .message("canned")
                    .body(body.toResponseBody("application/json".toMediaType()))
                    .build()
            }
            .build()
        return Retrofit.Builder()
            .baseUrl("http://10.0.2.2:8000/api/v1/")
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(VelroApi::class.java)
    }

    private fun refusal(code: String, context: String = "{}") =
        """{"success":false,"error":{"code":"$code","message_key":"error.${code.lowercase()}",
           "context":$context,"request_id":"req-1"}}""".trimIndent()

    @Test
    fun `it is a DELETE of the account itself`() = runTest {
        val seen = mutableListOf<Request>()
        val api = answering(200, """{"success":true,"data":{"deleted":true}}""", seen)

        mapper.call { api.deleteAccount() }

        val request = seen.single()
        assertEquals("DELETE", request.method)
        assertEquals("/api/v1/auth/me", request.url.encodedPath)
        assertNull("nothing is sent but the verb and the token", request.body)
    }

    @Test
    fun `a yes decodes as a success`() = runTest {
        val api = answering(200, """{"success":true,"data":{"deleted":true},"message":null,"meta":{}}""")

        val result = mapper.call { api.deleteAccount() }

        assertTrue("got $result", result is ApiResult.Success)
        assertEquals(true, (result as ApiResult.Success).value["deleted"])
    }

    @Test
    fun `each refusal arrives as its own code`() = runTest {
        val refusals = listOf(
            Triple("ACCOUNT_HAS_ACTIVE_BOOKING", 409, """{"user_id":"u","bookings":1}"""),
            Triple("ACCOUNT_HAS_ACTIVE_TRIP", 409, """{"user_id":"u","trip_id":"t"}"""),
            Triple("ACCOUNT_STAFF_UNDELETABLE", 403, """{"user_id":"u"}"""),
        )
        for ((code, status, context) in refusals) {
            val api = answering(status, refusal(code, context))

            val result = mapper.call { api.deleteAccount() }

            val error = (result as? ApiResult.Failure)?.error
            assertEquals("HTTP $status must come back as $code", code, error?.code)
            assertEquals(status, error?.httpStatus)
            assertFalse("$code is not a deletion", AuthRepository.alreadyDeleted(result))
        }
    }

    @Test
    fun `a retry that meets the account already gone is the deletion it asked for`() = runTest {
        // The first attempt worked and its answer was lost on the way back.
        // The retry carries the old token to an account the server has
        // closed, and is refused the way every request from it now is.
        val api = answering(401, refusal("USER_SUSPENDED", """{"user_id":"u","status":"DEACTIVATED"}"""))

        val result = mapper.call { api.deleteAccount() }

        assertTrue(AuthRepository.alreadyDeleted(result))
    }

    @Test
    fun `a suspended account is not mistaken for a deleted one`() = runTest {
        val api = answering(401, refusal("USER_SUSPENDED", """{"user_id":"u","status":"SUSPENDED"}"""))

        val result = mapper.call { api.deleteAccount() }

        assertFalse(AuthRepository.alreadyDeleted(result))
        assertFalse(AuthRepository.alreadyDeleted(ApiResult.Success(Unit)))
    }

    @Test
    fun `every locale can say why a deletion was refused`() {
        // A code the server can send with no sentence to render is a code the
        // person would see raw -- or, through forErrorCode's fallback, as a
        // general "something went wrong" that tells them nothing to do.
        for (tag in listOf("en", "fa-AF", "ps")) {
            val messages = localeFile(tag)
            for (code in listOf(
                "ACCOUNT_HAS_ACTIVE_BOOKING",
                "ACCOUNT_HAS_ACTIVE_TRIP",
                "ACCOUNT_STAFF_UNDELETABLE",
            )) {
                val key = "error." + code.lowercase()
                assertTrue("$tag is missing $key", messages.contains("\"$key\""))
            }
        }
    }

    private fun localeFile(tag: String): String {
        var dir: File? = File(System.getProperty("user.dir") ?: ".")
        while (dir != null) {
            val candidate = File(dir, "backend/resources/locales/$tag.json")
            if (candidate.isFile) return candidate.readText()
            dir = dir.parentFile
        }
        error("locale $tag not found")
    }
}
