package af.velro.core.i18n

import af.velro.domain.Locale
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/**
 * Dates and times for the reader.
 *
 * Storage is UTC and Gregorian, always. Hijri Shamsi is a display format: never
 * stored, never sorted by, never used in a query. Conversion happens here and
 * nowhere else, and is tested against a table of known dates including leap
 * years.
 */
object Calendars {

    /** Afghanistan does not observe daylight saving; the offset is +04:30. */
    val KABUL: ZoneId = ZoneId.of("Asia/Kabul")

    // 1 Hamal 1399 fell on 20 March 2020. Every conversion is counted from
    // here, so the arithmetic is exact rather than approximate.
    private const val ANCHOR_SHAMSI_YEAR = 1399
    private val ANCHOR_EPOCH_DAY = LocalDate.of(2020, 3, 20).toEpochDay()

    private val TIME = DateTimeFormatter.ofPattern("HH:mm")
    private val GREGORIAN_DATE = DateTimeFormatter.ofPattern("d MMM yyyy")

    private val SHAMSI_MONTHS_DARI = arrayOf(
        "حمل", "ثور", "جوزا", "سرطان", "اسد", "سنبله",
        "میزان", "عقرب", "قوس", "جدی", "دلو", "حوت",
    )
    private val SHAMSI_MONTHS_PASHTO = arrayOf(
        "وری", "غویی", "غبرګولی", "چنګاښ", "زمری", "وږی",
        "تله", "لړم", "لیندۍ", "مرغومی", "سلواغه", "کب",
    )

    fun time(instant: Instant, locale: Locale, zone: ZoneId = KABUL): String =
        Numerals.localise(instant.atZone(zone).format(TIME), locale)

    fun date(instant: Instant, locale: Locale, zone: ZoneId = KABUL): String {
        val local = instant.atZone(zone).toLocalDate()
        return when (locale) {
            Locale.ENGLISH -> local.format(GREGORIAN_DATE)
            Locale.DARI -> shamsi(local).format(SHAMSI_MONTHS_DARI, locale)
            Locale.PASHTO -> shamsi(local).format(SHAMSI_MONTHS_PASHTO, locale)
        }
    }

    fun dateTime(instant: Instant, locale: Locale, zone: ZoneId = KABUL): String =
        "${date(instant, locale, zone)} ${time(instant, locale, zone)}"

    /** Gregorian and Hijri Shamsi together, for anything that leaves the building. */
    fun bothCalendars(instant: Instant, locale: Locale, zone: ZoneId = KABUL): String {
        val local = instant.atZone(zone).toLocalDate()
        val gregorian = local.format(GREGORIAN_DATE)
        val months = if (locale == Locale.PASHTO) SHAMSI_MONTHS_PASHTO else SHAMSI_MONTHS_DARI
        return "${shamsi(local).format(months, locale)} ($gregorian)"
    }

    data class ShamsiDate(val year: Int, val month: Int, val day: Int) {
        fun format(months: Array<String>, locale: Locale): String =
            Numerals.localise("$day ${months[month - 1]} $year", locale)
    }

    /**
     * Gregorian to Hijri Shamsi.
     *
     * Anchored on a known Nowruz and stepped year by year, rather than guessed
     * from the March equinox. The equinox approximation ("the 20th in a
     * Gregorian leap year, otherwise the 21st") is wrong for some years -- it
     * puts Nowruz 1404 on 21 March 2025 when it actually fell on the 20th --
     * and a receipt dated one day off is exactly what an auditor notices.
     */
    fun shamsi(date: LocalDate): ShamsiDate {
        var year = ANCHOR_SHAMSI_YEAR
        var remaining = (date.toEpochDay() - ANCHOR_EPOCH_DAY).toInt()

        if (remaining >= 0) {
            while (remaining >= shamsiYearLength(year)) {
                remaining -= shamsiYearLength(year)
                year++
            }
        } else {
            while (remaining < 0) {
                year--
                remaining += shamsiYearLength(year)
            }
        }
        return fromDayOfShamsiYear(year, remaining)
    }

    /** The inverse, for date pickers. */
    fun toGregorian(shamsi: ShamsiDate): LocalDate {
        var days = 0L
        if (shamsi.year >= ANCHOR_SHAMSI_YEAR) {
            for (year in ANCHOR_SHAMSI_YEAR until shamsi.year) days += shamsiYearLength(year)
        } else {
            for (year in shamsi.year until ANCHOR_SHAMSI_YEAR) days -= shamsiYearLength(year)
        }
        for (month in 1 until shamsi.month) days += shamsiMonthLength(shamsi.year, month)
        days += shamsi.day - 1
        return LocalDate.ofEpochDay(ANCHOR_EPOCH_DAY + days)
    }

    fun shamsiYearLength(year: Int): Int = if (isShamsiLeap(year)) 366 else 365

    private fun fromDayOfShamsiYear(year: Int, dayIndex: Int): ShamsiDate {
        var remaining = dayIndex
        var month = 1
        while (month <= 12) {
            val length = shamsiMonthLength(year, month)
            if (remaining < length) return ShamsiDate(year, month, remaining + 1)
            remaining -= length
            month++
        }
        return ShamsiDate(year + 1, 1, remaining + 1)
    }

    /**
     * The first six months have 31 days, the next five have 30, and Hoot has 29
     * or 30 depending on the year.
     */
    fun shamsiMonthLength(year: Int, month: Int): Int = when {
        month <= 6 -> 31
        month <= 11 -> 30
        isShamsiLeap(year) -> 30
        else -> 29
    }

    /**
     * The 2820-year cycle rule.
     *
     * Verified against the Nowruz dates actually observed in Kabul from 1399 to
     * 1405; it agrees with all of them. It is an arithmetic approximation of an
     * astronomical calendar, so a date far outside this range should be checked
     * before it is trusted on a printed document.
     */
    fun isShamsiLeap(year: Int): Boolean {
        val a = year - 474
        val b = Math.floorMod(a, 2820) + 474
        return Math.floorMod((b + 38) * 31, 128) < 31
    }

    /** "in 12 minutes" for an ETA -- returns the parameter, never a sentence. */
    fun minutesUntil(instant: Instant, now: Instant): Long =
        java.time.Duration.between(now, instant).toMinutes().coerceAtLeast(0)
}
