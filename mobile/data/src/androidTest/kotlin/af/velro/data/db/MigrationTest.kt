package af.velro.data.db

import androidx.room.testing.MigrationTestHelper
import androidx.sqlite.db.framework.FrameworkSQLiteOpenHelperFactory
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Migrations run against a real database, from the exact schema that shipped.
 *
 * There is no destructive fallback, so a migration that does not work leaves a
 * passenger's phone with an app that cannot open. This opens a genuine
 * version-1 file, writes a booking into it, migrates, and reads the booking
 * back -- the only evidence that upgrading does not lose data.
 */
@RunWith(AndroidJUnit4::class)
class MigrationTest {

    @get:Rule
    val helper = MigrationTestHelper(
        InstrumentationRegistry.getInstrumentation(),
        VelroDatabase::class.java,
        emptyList(),
        FrameworkSQLiteOpenHelperFactory(),
    )

    @Test
    fun migrating_from_1_to_2_keeps_the_booking() {
        val db = helper.createDatabase(TEST_DB, 1)
        db.execSQL(
            """
            INSERT INTO bookings (
              id, number, tripId, status, rideKind, seatCount, seatNumbers,
              pickupStationId, dropoffDestinationId, fareTotalMinor,
              fareTotalCurrency, paymentMethod, verificationCode, createdAt, syncState
            ) VALUES (
              'b1', 'BKG-2026-000001', 't1', 'CONFIRMED', 'SHARED', 2, '1,2',
              's1', 'd1', 100000, 'AFN', 'CASH', 'LPMF', 1756000000000, 'SYNCED'
            )
            """.trimIndent()
        )
        db.close()

        val migrated = helper.runMigrationsAndValidate(TEST_DB, 2, true, MIGRATION_1_2)

        migrated.query("SELECT * FROM bookings WHERE id = 'b1'").use { cursor ->
            assertEquals(1, cursor.count)
            cursor.moveToFirst()
            // What the passenger already had must survive untouched.
            assertEquals(
                "BKG-2026-000001",
                cursor.getString(cursor.getColumnIndexOrThrow("number")),
            )
            assertEquals(100000L, cursor.getLong(cursor.getColumnIndexOrThrow("fareTotalMinor")))
            assertEquals("LPMF", cursor.getString(cursor.getColumnIndexOrThrow("verificationCode")))
            // A booking cached before the upgrade has no receipt detail; the
            // screen renders that as "not recorded" rather than crashing.
            assertEquals("[]", cursor.getString(cursor.getColumnIndexOrThrow("fareBreakdown")))
            assertNull(cursor.getString(cursor.getColumnIndexOrThrow("driverName")))
        }
    }

    private companion object {
        const val TEST_DB = "migration-test.db"
    }
}
