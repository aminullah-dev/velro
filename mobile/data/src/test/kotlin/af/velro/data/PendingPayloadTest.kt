package af.velro.data

import af.velro.data.sync.PendingPayloads
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The queue's writers held against its reader.
 *
 * A payload is written on a handset in a dead zone and read back minutes or
 * hours later by the sync worker. A drifted key name fails there -- the worst
 * possible place -- and no compiler connects the two sides, because both ends
 * are stringly JSON. These pin the exact key sets QueuedOperation.execute
 * reads, so a rename on either side fails here first.
 */
class PendingPayloadTest {

    private fun keys(payload: String): Set<String> =
        Json.parseToJsonElement(payload).jsonObject.keys

    @Test
    fun `booking payload carries exactly what the replayer reads`() {
        assertEquals(
            setOf(
                "trip_id", "seat_count", "pickup_station_id",
                "dropoff_destination_id", "note", "latitude", "longitude",
                "location_is_mock",
            ),
            keys(PendingPayloads.booking("t", 2, "s", "d", "note", "34.9", "68.7", true)),
        )
        // Optional fields are absent when null, not null-valued: the reader
        // uses jsonPrimitive.content, which would render the STRING "null".
        // An honest (non-mock) fix omits the brand the same way.
        assertEquals(
            setOf("trip_id", "seat_count", "pickup_station_id", "dropoff_destination_id"),
            keys(PendingPayloads.booking("t", 2, "s", "d", null, null, null, false)),
        )
    }

    @Test
    fun `cancel payload carries exactly what the replayer reads`() {
        assertEquals(
            setOf("booking_id", "reason_code"),
            keys(PendingPayloads.cancel("b", "PASSENGER_CANCELLED")),
        )
    }

    @Test
    fun `rating payload carries exactly what the replayer reads`() {
        assertEquals(
            setOf("trip_id", "score", "comment", "booking_id"),
            keys(PendingPayloads.rating("t", 5, "c", "b")),
        )
        assertEquals(
            setOf("trip_id", "score"),
            keys(PendingPayloads.rating("t", 5, null, null)),
        )
    }
}
