package af.velro.data.repository

import af.velro.data.api.ApiResult
import af.velro.data.api.ResponseMapper
import af.velro.data.api.SessionDto
import af.velro.data.api.TokenStore
import af.velro.data.api.VelroApi
import af.velro.data.db.BookingEntity
import af.velro.data.db.VelroDatabase
import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Protocol
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import retrofit2.Retrofit

/**
 * Deleting the account, and what the phone forgets when it does.
 *
 * The half of the feature a unit test cannot see: the cache and the session
 * are a real Room database and a real DataStore, and the property is that a
 * yes from the server leaves neither holding anything, while a refusal leaves
 * both exactly as they were. Instrumented for the reason SignOutTest is --
 * clearAllTables' main-thread check is Room's own, and a fake would have to
 * reimplement it to catch the crash it once caused.
 *
 * The server is an OkHttp interceptor answering in-process. Nothing here
 * opens a socket.
 */
@RunWith(AndroidJUnit4::class)
class DeleteAccountTest {

    private lateinit var db: VelroDatabase
    private lateinit var tokens: TokenStore
    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    }

    @Before
    fun open() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        // No allowMainThreadQueries: that flag is exactly what would hide the
        // crash signing out once had.
        db = Room.inMemoryDatabaseBuilder(context, VelroDatabase::class.java).build()
        tokens = TokenStore(context)
        runBlocking { tokens.save(aSession()) }
    }

    @After
    fun close() {
        runBlocking { tokens.clear() }
        db.close()
    }

    private fun repositoryAnswering(code: Int, body: String): AuthRepository {
        val client = OkHttpClient.Builder()
            .addInterceptor { chain ->
                Response.Builder()
                    .request(chain.request())
                    .protocol(Protocol.HTTP_1_1)
                    .code(code)
                    .message("canned")
                    .body(body.toResponseBody("application/json".toMediaType()))
                    .build()
            }
            .build()
        val api = Retrofit.Builder()
            .baseUrl("http://127.0.0.1:1/api/v1/")
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(VelroApi::class.java)
        return AuthRepository(api, tokens, db, ResponseMapper(json))
    }

    @Test
    fun a_deleted_account_leaves_nothing_on_the_phone() = runBlocking {
        db.bookings().upsert(aBooking())
        val auth = repositoryAnswering(200, """{"success":true,"data":{"deleted":true}}""")

        // From the main thread, as the screen's ViewModel calls it.
        val result = withContext(Dispatchers.Main) { auth.deleteAccount() }

        assertTrue("got $result", result is ApiResult.Success)
        assertEquals(
            "the account's journeys must not outlive it on this phone",
            0,
            db.bookings().cachedByStatus(listOf("CONFIRMED"), 10).size,
        )
        assertNull("the session must be gone", tokens.currentAccessToken())
        assertNull(tokens.currentRefreshToken())
        assertTrue("sign-in must be told why it is showing", auth.accountDeleted.value)

        auth.acknowledgeAccountDeleted()
        assertFalse("and told once", auth.accountDeleted.value)
    }

    @Test
    fun a_refusal_leaves_the_account_exactly_as_it_was() = runBlocking {
        for ((code, status) in listOf(
            "ACCOUNT_HAS_ACTIVE_BOOKING" to 409,
            "ACCOUNT_HAS_ACTIVE_TRIP" to 409,
            "ACCOUNT_STAFF_UNDELETABLE" to 403,
        )) {
            db.bookings().upsert(aBooking())
            val auth = repositoryAnswering(
                status,
                """{"success":false,"error":{"code":"$code","context":{}}}""",
            )

            val result = withContext(Dispatchers.Main) { auth.deleteAccount() }

            assertEquals(code, (result as? ApiResult.Failure)?.error?.code)
            assertNotNull("$code must not sign anybody out", tokens.currentAccessToken())
            assertEquals(1, db.bookings().cachedByStatus(listOf("CONFIRMED"), 10).size)
            assertFalse("$code is not a deletion", auth.accountDeleted.value)
        }
    }

    @Test
    fun a_retry_that_finds_the_account_gone_still_forgets_it() = runBlocking {
        db.bookings().upsert(aBooking())
        val auth = repositoryAnswering(
            401,
            """{"success":false,"error":{"code":"USER_SUSPENDED",
               "context":{"user_id":"u","status":"DEACTIVATED"}}}""",
        )

        val result = withContext(Dispatchers.Main) { auth.deleteAccount() }

        assertTrue("got $result", result is ApiResult.Success)
        assertEquals(0, db.bookings().cachedByStatus(listOf("CONFIRMED"), 10).size)
        assertNull(tokens.currentAccessToken())
        assertTrue(auth.accountDeleted.value)
    }

    private fun aSession() = SessionDto(
        user_id = "01900000-0000-7000-8000-0000000000aa",
        access_token = "access",
        refresh_token = "refresh",
        roles = listOf("PASSENGER"),
        is_new_user = false,
        expires_in_seconds = 900,
    )

    private fun aBooking() = BookingEntity(
        id = "01900000-0000-7000-8000-000000000001",
        number = "BKG-2026-000001",
        tripId = "01900000-0000-7000-8000-000000000002",
        status = "CONFIRMED",
        rideKind = "SHARED",
        seatCount = 1,
        seatNumbers = "1",
        pickupStationId = "01900000-0000-7000-8000-000000000003",
        dropoffDestinationId = "01900000-0000-7000-8000-000000000004",
        fareTotalMinor = 32000,
        fareTotalCurrency = "AFN",
        paymentMethod = "CASH",
        verificationCode = "VJEL",
        createdAt = 0L,
    )
}
