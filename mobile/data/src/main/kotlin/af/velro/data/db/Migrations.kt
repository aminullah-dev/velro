package af.velro.data.db

import androidx.room.migration.Migration
import androidx.sqlite.db.SupportSQLiteDatabase

/**
 * Forward-only, one per schema change.
 *
 * There is no destructive fallback: wiping a passenger's cached bookings and a
 * driver's offline queue because a migration was not written is not an upgrade
 * path. Every migration here has a test that opens a real version-1 database,
 * runs it, and reads the data back.
 */
val MIGRATION_1_2 = object : Migration(1, 2) {
    override fun migrate(db: SupportSQLiteDatabase) {
        // Receipt fields. All nullable or defaulted, so existing rows survive
        // untouched: a booking cached before the upgrade simply has no driver
        // recorded, which the screen already renders as "not yet assigned".
        for (column in listOf(
            "fareBreakdown TEXT NOT NULL DEFAULT '[]'",
            "pickupStationName TEXT",
            "dropoffDestinationName TEXT",
            "tripNumber TEXT",
            "scheduledDepartureAt INTEGER",
            "driverName TEXT",
            "vehiclePlate TEXT",
            "vehicleDescription TEXT",
            "completedAt INTEGER",
            "cancelledAt INTEGER",
            "cancellationReasonCode TEXT",
            "cancellationFeeMinor INTEGER",
        )) {
            db.execSQL("ALTER TABLE bookings ADD COLUMN $column")
        }
    }
}

val ALL_MIGRATIONS = arrayOf(MIGRATION_1_2)
