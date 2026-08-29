package af.velro.data

import af.velro.data.api.BookingDto
import af.velro.data.api.DestinationGroupDto
import af.velro.data.api.DistrictDto
import af.velro.data.api.DriverProfileDto
import af.velro.data.api.EarningsDto
import af.velro.data.api.Envelope
import af.velro.data.api.ErrorEnvelope
import af.velro.data.api.GeoSnapshotDto
import af.velro.data.api.ProfileDto
import af.velro.data.api.StationDto
import af.velro.data.api.TripOptionDto
import af.velro.data.api.VillageDto
import af.velro.data.repository.toDomain
import java.io.File
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The wire contract, checked against real server responses.
 *
 * The fixtures in `src/test/resources/contract/` were captured from a running
 * VELRO backend, not hand-written -- a hand-written fixture only ever proves
 * that the DTOs match themselves.
 *
 * This exists because of a real bug: the DTOs declared `latitude` as a String
 * while the server sends a JSON number. The decode failed, the failure was
 * reported to the passenger as "your connection is weak", and the app showed an
 * empty district list on a perfectly good connection. Nothing in the app or the
 * server was individually wrong; only the seam between them was, and only a
 * test that reads a real payload can see it.
 *
 * Re-capture the fixtures whenever the API changes: `scripts/capture-contract.sh`.
 */
class ApiContractTest {

    private val json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    }

    private fun fixture(name: String): String {
        var dir: File? = File(System.getProperty("user.dir"))
        while (dir != null) {
            val candidate = File(dir, "data/src/test/resources/contract/$name")
            if (candidate.isFile) return candidate.readText()
            dir = dir.parentFile
        }
        error("fixture $name not found")
    }

    private inline fun <reified T> decode(name: String): T =
        json.decodeFromString<Envelope<T>>(fixture(name)).data
            ?: error("$name had no data")

    @Test
    fun `the geography snapshot decodes`() {
        val snapshot = decode<GeoSnapshotDto>("geo_snapshot.json")

        assertTrue("districts", snapshot.districts.isNotEmpty())
        assertTrue("villages", snapshot.villages.isNotEmpty())
        assertTrue("stations", snapshot.stations.isNotEmpty())
        assertTrue("destinations", snapshot.destinations.isNotEmpty())
        assertTrue("version", snapshot.version.isNotBlank())
    }

    @Test
    fun `coordinates arrive as numbers and survive the mapping`() {
        // The exact bug this file exists for.
        val snapshot = decode<GeoSnapshotDto>("geo_snapshot.json")
        val located = snapshot.stations.firstOrNull { it.latitude != null }
        assertNotNull("the fixture must contain at least one located station", located)

        val station = located!!.toDomain()
        assertNotNull(station.latitude)
        assertTrue("latitude in range", station.latitude!! in -90.0..90.0)
        assertTrue("longitude in range", station.longitude!! in -180.0..180.0)
        // Ghorband is in Parwan; a coordinate outside this box means the
        // mapping has silently swapped or truncated something.
        assertTrue("latitude near Ghorband", station.latitude!! in 30.0..40.0)
        assertTrue("longitude near Ghorband", station.longitude!! in 60.0..75.0)
    }

    @Test
    fun `districts decode with their alternative names`() {
        val districts = decode<List<DistrictDto>>("districts.json")
        assertEquals("the four Ghorband districts", 4, districts.size)
        assertTrue(districts.all { it.code.startsWith("GRB-") })
        assertTrue(
            "an alternative name should survive",
            districts.any { !it.alternative_name.isNullOrBlank() },
        )
    }

    @Test
    fun `villages and stations decode`() {
        assertTrue(decode<List<VillageDto>>("villages.json").isNotEmpty())
        val stations = decode<List<StationDto>>("stations.json")
        assertTrue(stations.isNotEmpty())
        assertTrue("a village has a primary station", stations.any { it.is_primary })
    }

    @Test
    fun `destination groups keep Kabul's children`() {
        val groups = decode<List<DestinationGroupDto>>("destination_groups.json")
        assertTrue(groups.isNotEmpty())
        val kabul = groups.firstOrNull { it.children.isNotEmpty() }
        assertNotNull("Kabul must arrive with its children (section 16)", kabul)
        assertEquals(2, kabul!!.children.size)
    }

    @Test
    fun `trip options decode with money as an object`() {
        val options = decode<List<TripOptionDto>>("trip_options.json")
        assertTrue("the fixture must contain trips", options.isNotEmpty())

        val option = options.first()
        assertNotNull("a fare must be present", option.fare_total)
        // Money is an object of integer minor units, never a decimal string and
        // never a float.
        assertEquals("AFN", option.fare_total!!.currency)
        assertTrue(option.fare_total!!.amount_minor > 0)

        val domain = option.toDomain()
        assertEquals(option.fare_total!!.amount_minor, domain.fareTotal!!.amountMinor)
        assertTrue("departure parsed", domain.scheduledDepartureAt.epochSecond > 0)
        assertTrue("status parsed", domain.seatCapacity > 0)
    }

    @Test
    fun `a booking decodes with its seats and fare`() {
        val bookings = decode<List<BookingDto>>("bookings.json")
        assertTrue("the fixture must contain a booking", bookings.isNotEmpty())

        val booking = bookings.first().toDomain()
        assertTrue(booking.number.startsWith("BKG-"))
        assertEquals(booking.seatCount, booking.seatNumbers.size)
        assertTrue(booking.fareTotal.amountMinor > 0)
        assertNotNull("the owner sees their boarding code", booking.verificationCode)
    }

    @Test
    fun `the driver profile and earnings decode`() {
        val profile = decode<DriverProfileDto>("driver_profile.json").toDomain()
        assertNotNull(profile.vehicle)
        assertTrue("an approved seeded driver can work", profile.canWork)

        val earnings = decode<EarningsDto>("earnings.json").toDomain()
        assertEquals("AFN", earnings.available.currency)
    }

    @Test
    fun `the profile decodes`() {
        val profile = decode<ProfileDto>("profile.json")
        assertTrue(profile.phone.startsWith("+93"))
        assertTrue("PASSENGER" in profile.roles)
    }

    @Test
    fun `an error envelope decodes into a code and a message key`() {
        val envelope = json.decodeFromString<ErrorEnvelope>(fixture("error_envelope.json"))
        assertTrue(envelope.error.code.isNotBlank())
        assertEquals(
            "the key is derived from the code, so no code can be untranslatable",
            "error." + envelope.error.code.lowercase(),
            envelope.error.messageKey,
        )
        assertNotNull("support asks for the request id", envelope.error.requestId)
    }

    @Test
    fun `every locale has a message for the codes the fixtures carry`() {
        // Ties the wire contract to the translations: a code the server can
        // send with no key to render is a code a passenger would see raw.
        val envelope = json.decodeFromString<ErrorEnvelope>(fixture("error_envelope.json"))
        val key = "error." + envelope.error.code.lowercase()

        for (tag in listOf("en", "fa-AF", "ps")) {
            val locales = localeFile(tag)
            assertTrue("$tag is missing $key", locales.contains("\"$key\""))
        }
    }

    private fun localeFile(tag: String): String {
        var dir: File? = File(System.getProperty("user.dir"))
        while (dir != null) {
            val candidate = File(dir, "backend/resources/locales/$tag.json")
            if (candidate.isFile) return candidate.readText()
            dir = dir.parentFile
        }
        error("locale $tag not found")
    }
}
