package af.velro.core.i18n

import af.velro.domain.Locale
import java.io.File
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.boolean
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Calendar conversion against a table of known dates.
 *
 * A receipt dated one day off is exactly the sort of defect that is noticed by
 * an auditor and by nobody else beforehand, so the leap years are here too.
 */
class CalendarTest {

    @Test
    fun `known gregorian dates convert to the right shamsi date`() {
        val cases = listOf(
            // Nowruz: 1 Hamal.
            Triple(LocalDate.of(2026, 3, 21), 1405, 1),
            // The day before Nowruz is the last day of Hoot.
            Triple(LocalDate.of(2026, 3, 20), 1404, 12),
            // Mid-year.
            Triple(LocalDate.of(2026, 8, 29), 1405, 6),
            Triple(LocalDate.of(2026, 1, 1), 1404, 10),
        )
        for ((gregorian, year, month) in cases) {
            val shamsi = Calendars.shamsi(gregorian)
            assertEquals("year for $gregorian", year, shamsi.year)
            assertEquals("month for $gregorian", month, shamsi.month)
            assertTrue("day for $gregorian", shamsi.day in 1..31)
        }
    }

    @Test
    fun `month lengths follow the six thirty-one rule`() {
        for (month in 1..6) assertEquals(31, Calendars.shamsiMonthLength(1404, month))
        for (month in 7..11) assertEquals(30, Calendars.shamsiMonthLength(1404, month))
        assertTrue(Calendars.shamsiMonthLength(1404, 12) in 29..30)
    }

    @Test
    fun `a shamsi year has 365 or 366 days`() {
        for (year in 1400..1420) {
            val total = (1..12).sumOf { Calendars.shamsiMonthLength(year, it) }
            assertTrue("year $year had $total days", total == 365 || total == 366)
            assertEquals(Calendars.isShamsiLeap(year), total == 366)
        }
    }

    @Test
    fun `nowruz falls on the observed gregorian dates`() {
        // Read from the shared file rather than retyped here. The previous
        // version of this test listed Nowruz 1404 as 20 March 2025 because that
        // is what the implementation produced -- the test was written from the
        // code instead of from the calendar, so it agreed with the bug and hid
        // it. The dates now live in one place, next to the note saying where
        // they came from.
        for ((year, gregorian) in spec.nowruz) {
            val shamsi = Calendars.shamsi(gregorian)
            assertEquals("Nowruz $year year", year, shamsi.year)
            assertEquals("Nowruz $year month", 1, shamsi.month)
            assertEquals("Nowruz $year day", 1, shamsi.day)
        }
    }

    @Test
    fun `leap years match the observed calendar`() {
        for ((year, leap) in spec.leapYears) {
            assertEquals("leap for $year", leap, Calendars.isShamsiLeap(year))
        }
    }

    @Test
    fun `a leap year is exactly the year whose nowruz is 366 days after the last`() {
        // The definition, not a second opinion: if the observed Nowruz dates
        // are 366 days apart the year between them had a leap day, whatever any
        // cycle rule says.
        var measured = 0
        for (year in spec.nowruz.keys.sorted()) {
            // The table has gaps -- only years whose successor is also listed
            // can be measured this way.
            val next = spec.nowruz[year + 1] ?: continue
            measured++
            val span = ChronoUnit.DAYS.between(spec.nowruz[year], next)
            assertEquals(
                "span after Nowruz $year",
                if (Calendars.isShamsiLeap(year)) 366L else 365L,
                span,
            )
        }
        assertTrue("no year spans were measured at all", measured > 5)
    }

    @Test
    fun `the shared conversion table holds`() {
        for (case in spec.conversions) {
            val shamsi = Calendars.shamsi(case.gregorian)
            assertEquals(
                "${case.gregorian} (${case.note})",
                Calendars.ShamsiDate(case.year, case.month, case.day),
                shamsi,
            )
        }
    }

    @Test
    fun `conversion round-trips both ways`() {
        var date = LocalDate.of(2020, 1, 1)
        while (date < LocalDate.of(2030, 1, 1)) {
            val shamsi = Calendars.shamsi(date)
            assertEquals("round trip for $date", date, Calendars.toGregorian(shamsi))
            date = date.plusDays(1)
        }
    }

    @Test
    fun `eastern digits are used for dari and pashto but not english`() {
        Numerals.useEasternDigits = null
        assertEquals("۱۲۳", Numerals.localise("123", Locale.DARI))
        assertEquals("۱۲۳", Numerals.localise("123", Locale.PASHTO))
        assertEquals("123", Numerals.localise("123", Locale.ENGLISH))
    }

    @Test
    fun `a preference overrides the per-locale default`() {
        try {
            Numerals.useEasternDigits = false
            assertEquals("123", Numerals.localise("123", Locale.DARI))
        } finally {
            Numerals.useEasternDigits = null
        }
    }

    @Test
    fun `eastern digits round-trip back to latin`() {
        assertEquals("+93700123456", Numerals.latin("+۹۳۷۰۰۱۲۳۴۵۶"))
    }


    @Test
    fun `the shamsi month names match the locale files`() {
        // Calendars keeps its own arrays so that formatting needs no dictionary
        // lookup, which is the right trade for a screen that renders a list.
        // The cost is a second copy of twelve strings, and this is what stops it
        // drifting from the copy the admin panel reads.
        val expected = mapOf(
            "fa-AF" to Locale.DARI,
            "ps" to Locale.PASHTO,
        )
        for ((tag, locale) in expected) {
            val dictionary = Json.parseToJsonElement(localeFile(tag).readText()).jsonObject
            for (month in 1..12) {
                val key = "common.shamsi_month.$month"
                val fromFile = dictionary[key]?.jsonPrimitive?.content
                assertNotNull("$tag is missing $key", fromFile)
                // Rendered through a known date so the array is read the same
                // way the app reads it.
                val nowruz = Calendars.shamsi(spec.nowruz[1405]!!)
                val rendered = Calendars.ShamsiDate(nowruz.year, month, 1)
                assertTrue(
                    "$tag $key: the app renders '${format(rendered, locale)}', " +
                        "the locale file says '$fromFile'",
                    format(rendered, locale).contains(fromFile!!),
                )
            }
        }
    }

    private fun format(date: Calendars.ShamsiDate, locale: Locale): String =
        Calendars.date(
            Calendars.toGregorian(date).atStartOfDay(Calendars.KABUL).toInstant(),
            locale,
        )

    private fun localeFile(tag: String): File {
        var dir: File? = File(System.getProperty("user.dir"))
        while (dir != null) {
            val candidate = File(dir, "backend/resources/locales/$tag.json")
            if (candidate.isFile) return candidate
            dir = dir.parentFile
        }
        error("backend/resources/locales/$tag.json not found")
    }

    // ---- the shared specification -------------------------------------------

    private data class Conversion(
        val gregorian: LocalDate,
        val year: Int,
        val month: Int,
        val day: Int,
        val note: String,
    )

    private class Spec(
        val nowruz: Map<Int, LocalDate>,
        val leapYears: Map<Int, Boolean>,
        val conversions: List<Conversion>,
    )

    private val spec: Spec by lazy { readSpec() }

    private fun readSpec(): Spec {
        // Walks up to the repository root and reads the real file -- never a
        // copy, which could go stale without anyone noticing.
        var dir: File? = File(System.getProperty("user.dir"))
        var found: File? = null
        while (dir != null && found == null) {
            val candidate = File(dir, "docs/domain/calendar.json")
            if (candidate.isFile) found = candidate
            dir = dir.parentFile
        }
        val file = found
            ?: error("docs/domain/calendar.json not found from ${System.getProperty("user.dir")}")
        val root = Json.parseToJsonElement(file.readText()).jsonObject

        val nowruz = root["nowruz"]!!.jsonObject.entries.associate { (year, value) ->
            year.toInt() to LocalDate.parse(value.jsonPrimitive.content)
        }
        val leapYears = root["leap_years"]!!.jsonObject.entries
            .filterNot { it.key.startsWith("$") }
            .associate { (year, value) -> year.toInt() to value.jsonPrimitive.boolean }
        val conversions = root["conversions"]!!.jsonArray.map { element ->
            val case = element.jsonObject
            val parts = case["shamsi"]!!.jsonArray.map { it.jsonPrimitive.int }
            Conversion(
                gregorian = LocalDate.parse(case["gregorian"]!!.jsonPrimitive.content),
                year = parts[0],
                month = parts[1],
                day = parts[2],
                note = case["note"]!!.jsonPrimitive.content,
            )
        }
        return Spec(nowruz, leapYears, conversions)
    }
}
