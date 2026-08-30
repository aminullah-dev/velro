package af.velro.data.repository

import af.velro.data.api.ResponseMapper
import af.velro.data.api.TokenStore
import af.velro.data.api.VelroApi
import af.velro.data.db.BookingEntity
import af.velro.data.db.VelroDatabase
import androidx.room.Room
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import retrofit2.Retrofit

/**
 * Signing out, from the thread the app actually calls it on.
 *
 * MainActivity calls signOut from a rememberCoroutineScope, which is the main
 * thread, and clearAllTables is Room's one blocking call -- every other access
 * in this layer is a suspend DAO, which Room moves off the main thread itself.
 * So tapping "برآمدن" threw IllegalStateException and killed both apps, every
 * time, for everybody.
 *
 * It threw between clearing the session and wiping the cache, leaving the
 * handset signed out with the previous person's journeys still on it -- the one
 * outcome sign-out exists to prevent on a phone the family shares.
 *
 * Instrumented rather than a unit test on purpose: the assertion that fires is
 * Room's own, and it only exists against a real database not built with
 * allowMainThreadQueries. A fake would have to reimplement the very check that
 * caught this, and would then be free to get it wrong.
 */
@RunWith(AndroidJUnit4::class)
class SignOutTest {

    private lateinit var db: VelroDatabase
    private lateinit var auth: AuthRepository

    @Before
    fun open() {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        // No allowMainThreadQueries: that flag is exactly what would hide this.
        db = Room.inMemoryDatabaseBuilder(context, VelroDatabase::class.java).build()

        val json = Json { ignoreUnknownKeys = true }
        // signOut(allDevices = false) never touches the network, so this is
        // built with no converter and an unreachable address: a test that
        // starts making calls fails loudly rather than quietly growing a
        // dependency on a running server.
        val api = Retrofit.Builder()
            .baseUrl("http://127.0.0.1:1/")
            .build()
            .create(VelroApi::class.java)

        auth = AuthRepository(api, TokenStore(context), db, ResponseMapper(json))
    }

    @After
    fun close() = db.close()

    @Test
    fun signing_out_from_the_main_thread_does_not_kill_the_app() = runBlocking {
        db.bookings().upsert(aBooking())
        assertEquals(1, db.bookings().cachedByStatus(listOf("CONFIRMED"), 10).size)

        withContext(Dispatchers.Main) { auth.signOut() }

        assertEquals(
            "the next person on this handset must not see the last one's journeys",
            0,
            db.bookings().cachedByStatus(listOf("CONFIRMED"), 10).size,
        )
    }

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
