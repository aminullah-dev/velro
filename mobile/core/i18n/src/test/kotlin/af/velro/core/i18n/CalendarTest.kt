package af.velro.core.i18n

import af.velro.domain.Locale
import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
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
    fun `leap years match the observed calendar`() {
        // Checked against the Nowruz dates themselves: 1403 ran 20 Mar 2024 to
        // 20 Mar 2025, which is 365 days, so it is not leap. 1404 ran to
        // 21 Mar 2026, which is 366.
        assertFalse(Calendars.isShamsiLeap(1403))
        assertTrue(Calendars.isShamsiLeap(1404))
        assertTrue(Calendars.isShamsiLeap(1399))
    }

    @Test
    fun `nowruz falls on the observed gregorian dates`() {
        // The dates people in Kabul actually kept.
        val observed = mapOf(
            1399 to LocalDate.of(2020, 3, 20),
            1400 to LocalDate.of(2021, 3, 21),
            1401 to LocalDate.of(2022, 3, 21),
            1402 to LocalDate.of(2023, 3, 21),
            1403 to LocalDate.of(2024, 3, 20),
            1404 to LocalDate.of(2025, 3, 20),
            1405 to LocalDate.of(2026, 3, 21),
        )
        for ((year, gregorian) in observed) {
            val shamsi = Calendars.shamsi(gregorian)
            assertEquals("Nowruz $year year", year, shamsi.year)
            assertEquals("Nowruz $year month", 1, shamsi.month)
            assertEquals("Nowruz $year day", 1, shamsi.day)
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
}
