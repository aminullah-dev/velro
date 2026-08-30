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

val MIGRATION_2_3 = object : Migration(2, 3) {
    override fun migrate(db: SupportSQLiteDatabase) {
        // Village aliases, so browsing offline finds a place by the name the
        // passenger uses. Defaulted rather than nullable: an empty string means
        // "no other names", which is the truth for most villages, and saves
        // every read site a null check.
        db.execSQL("ALTER TABLE villages ADD COLUMN alternativeNames TEXT NOT NULL DEFAULT ''")
    }
}

val MIGRATION_3_4 = object : Migration(3, 4) {
    override fun migrate(db: SupportSQLiteDatabase) {
        // The driver's number, so a passenger standing at a station with no
        // signal can still ring the man who is coming for her -- which is
        // exactly when she cannot reach the server to ask for it.
        //
        // Nullable rather than defaulted: the server sends it only while the
        // journey is ahead, and "we were never told" is a different fact from
        // "there is no number", which is what an empty string would say.
        db.execSQL("ALTER TABLE bookings ADD COLUMN driverPhone TEXT")
    }
}

val ALL_MIGRATIONS = arrayOf(MIGRATION_1_2, MIGRATION_2_3, MIGRATION_3_4)
