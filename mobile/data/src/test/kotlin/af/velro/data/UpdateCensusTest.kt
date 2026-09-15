package af.velro.data

import af.velro.data.api.ResponseMapper
import af.velro.data.api.VelroApi
import af.velro.data.release.UpdateRepository
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import okhttp3.HttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Test
import retrofit2.Retrofit

/**
 * What the launch-time update check tells the server about the build asking.
 *
 * A sideloaded APK has no store console counting installs, so this query
 * string is the only way anyone learns whether a fix reached the phones. The
 * request is caught by an interceptor before it leaves, through the real
 * Retrofit interface and the real repository, so what is asserted is what
 * would be on the wire -- with no server and no network.
 */
class UpdateCensusTest {

    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    }

    private var seen: HttpUrl? = null

    private val updates: UpdateRepository by lazy {
        val client = OkHttpClient.Builder()
            .addInterceptor { chain ->
                seen = chain.request().url
                Response.Builder()
                    .request(chain.request())
                    .protocol(Protocol.HTTP_1_1)
                    .code(200)
                    .message("OK")
                    .body(
                        """{"success":true,"data":{"available":false}}"""
                            .toResponseBody("application/json".toMediaType())
                    )
                    .build()
            }
            .build()
        val api = Retrofit.Builder()
            .baseUrl("http://localhost/api/v1/")
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(VelroApi::class.java)
        UpdateRepository(api, ResponseMapper(json))
    }

    @Test
    fun `the driver's build is named in the query`() = runTest {
        updates.availableUpdate("driver", currentCode = 6, currentName = "1.2.3")

        assertNotNull("the update check must still be asked", seen)
        val url = seen!!
        assertEquals("/api/v1/app/version", url.encodedPath)
        assertEquals(
            "app=driver&platform=android&version_code=6&version_name=1.2.3",
            url.encodedQuery,
        )
    }

    @Test
    fun `the passenger's build is named in the query`() = runTest {
        updates.availableUpdate("passenger", currentCode = 5, currentName = "1.2.2")

        val url = seen!!
        assertEquals("passenger", url.queryParameter("app"))
        assertEquals("android", url.queryParameter("platform"))
        assertEquals("5", url.queryParameter("version_code"))
        assertEquals("1.2.2", url.queryParameter("version_name"))
    }

    @Test
    fun `an app the repository does not know is left uncounted, not guessed`() = runTest {
        updates.availableUpdate("Passenger ", currentCode = 5, currentName = "1.2.2")

        assertNotNull("the update check must still be asked", seen)
        val url = seen!!
        assertEquals("/api/v1/app/version", url.encodedPath)
        assertNull("no census parameters at all", url.encodedQuery)
    }
}
