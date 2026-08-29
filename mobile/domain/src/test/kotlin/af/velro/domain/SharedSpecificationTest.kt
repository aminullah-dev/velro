package af.velro.domain

import java.io.File
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The Kotlin domain against the shared specification.
 *
 * `docs/domain/lifecycles.json` is the one source of truth for every lifecycle
 * in VELRO, and the Python domain is tested against the same file. platform-core
 * says a Python and a Kotlin domain cannot share code, so they share the
 * *specification* instead -- and divergence becomes a failing test rather than
 * a bug someone finds in Ghorband.
 */
class SharedSpecificationTest {

    private val spec: JsonObject by lazy {
        Json.parseToJsonElement(specFile().readText()).jsonObject
    }

    private fun specFile(): File {
        // Walks up to the repository root and reads the real file -- never a
        // copy, which could go stale without anyone noticing.
        var dir: File? = File(System.getProperty("user.dir"))
        while (dir != null) {
            val candidate = File(dir, "docs/domain/lifecycles.json")
            if (candidate.isFile) return candidate
            dir = dir.parentFile
        }
        error("docs/domain/lifecycles.json not found from ${System.getProperty("user.dir")}")
    }

    private fun section(name: String): JsonObject = spec[name]!!.jsonObject

    private fun stringList(element: kotlinx.serialization.json.JsonElement): List<String> =
        (element as JsonArray).map { it.jsonPrimitive.content }

    private fun <S : Enum<S>> assertMatchesSpec(
        name: String,
        machine: StateMachine<S>,
        values: List<S>,
    ) {
        val declared = section(name)["transitions"]!!.jsonObject

        assertEquals(
            "$name: the states in code and in the specification differ",
            declared.keys.sorted(),
            values.map { it.name }.sorted(),
        )
        for ((state, allowed) in declared) {
            val current = values.first { it.name == state }
            assertEquals(
                "$name.$state",
                stringList(allowed).sorted(),
                machine.allowedFrom(current).map { it.name }.sorted(),
            )
        }
        assertEquals(
            "$name: error code",
            section(name)["error_code"]!!.jsonPrimitive.content,
            machine.errorCode,
        )
    }

    @Test
    fun `trip transitions match the specification`() {
        assertMatchesSpec("trip", Lifecycles.trip, TripStatus.entries)
    }

    @Test
    fun `booking transitions match the specification`() {
        assertMatchesSpec("booking", Lifecycles.booking, BookingStatus.entries)
    }

    @Test
    fun `settlement transitions match the specification`() {
        assertMatchesSpec("settlement", Lifecycles.settlement, SettlementStatus.entries)
    }

    @Test
    fun `the ticket machine matches the specification`() {
        assertMatchesSpec("ticket", Lifecycles.ticket, TicketStatus.entries)
    }

    @Test
    fun `every machine in the specification is actually mirrored here`() {
        // The tests above name their machines one at a time, so the list can
        // fall behind the file. A machine added to lifecycles.json and not to
        // this class is not a failing test -- it is no test at all, which is
        // worse: the suite goes green and nobody learns the mirror was never
        // checked.
        val declared = spec.entries
            .filter { !it.key.startsWith("$") }
            .filter { (it.value as? JsonObject)?.containsKey("transitions") == true }
            .map { it.key }
            .toSortedSet()
        val covered = sortedSetOf("trip", "booking", "settlement", "ticket")
        assertEquals(
            "lifecycles.json and this test disagree about which machines exist",
            covered,
            declared,
        )
    }

    @Test
    fun `bookable trip statuses match the specification`() {
        assertEquals(
            stringList(section("trip")["bookable_in"]!!).sorted(),
            Lifecycles.bookableTripStatuses.map { it.name }.sorted(),
        )
    }

    @Test
    fun `cancellable booking statuses match the specification`() {
        assertEquals(
            stringList(section("booking")["cancellable_in"]!!).sorted(),
            Lifecycles.cancellableBookingStatuses.map { it.name }.sorted(),
        )
    }

    @Test
    fun `the trip to booking cascade matches the specification`() {
        val declared = section("trip_to_booking")
            .filterKeys { !it.startsWith("$") }
            .mapValues { it.value.jsonPrimitive.content }
        val actual = Lifecycles.tripToBooking.entries.associate { it.key.name to it.value.name }
        assertEquals(declared, actual)
    }

    @Test
    fun `seat statuses match the specification`() {
        assertEquals(
            stringList(section("seat")["statuses"]!!).sorted(),
            SeatStatus.entries.map { it.name }.sorted(),
        )
    }

    @Test
    fun `commission rounding matches the server exactly`() {
        // A split that rounds differently in the app and on the server loses a
        // driver one afghani at a time, and they will notice.
        val cases = section("commission")["cases"]!!.jsonArray
        assertTrue("the specification must carry commission cases", cases.isNotEmpty())

        for (element in cases) {
            val case = element.jsonObject
            val gross = case["gross_minor"]!!.jsonPrimitive.long
            val rate = case["rate_basis_points"]!!.jsonPrimitive.int
            val split = CommissionSplit.of(MoneyValue(gross), rate)

            assertEquals(
                "platform share for $gross at $rate bp",
                case["platform_minor"]!!.jsonPrimitive.long,
                split.platform.amountMinor,
            )
            assertEquals(
                "driver share for $gross at $rate bp",
                case["driver_minor"]!!.jsonPrimitive.long,
                split.driver.amountMinor,
            )
            assertEquals(gross, split.platform.amountMinor + split.driver.amountMinor)
        }
    }

    @Test
    fun `a lagging booking catches up through the declared path`() {
        val route = Lifecycles.booking.path(BookingStatus.CONFIRMED, BookingStatus.READY)
        assertNotNull(route)
        assertEquals(listOf(BookingStatus.DRIVER_ASSIGNED, BookingStatus.READY), route)
    }

    @Test
    fun `a moving vehicle cannot be cancelled`() {
        assertFalse(Lifecycles.trip.can(TripStatus.IN_TRANSIT, TripStatus.CANCELLED))
    }

    @Test
    fun `terminal states allow nothing`() {
        assertTrue(Lifecycles.trip.terminalStates.isNotEmpty())
        for (state in Lifecycles.trip.terminalStates) {
            assertTrue(Lifecycles.trip.allowedFrom(state).isEmpty())
        }
    }
}
