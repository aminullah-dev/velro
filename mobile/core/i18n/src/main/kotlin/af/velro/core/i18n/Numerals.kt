package af.velro.core.i18n

import af.velro.domain.Locale
import af.velro.domain.MoneyValue
import af.velro.domain.minorDigits
import java.math.BigDecimal

/**
 * Numerals and money, formatted for the reader.
 *
 * Storage is always Latin digits; this is a display concern only. Dari and
 * Pashto readers generally expect Eastern Arabic-Indic digits in prose and
 * Latin digits in tables of figures, so the choice is a preference with a
 * per-locale default rather than an assumption.
 */
object Numerals {

    private const val EASTERN = "۰۱۲۳۴۵۶۷۸۹"

    /** Set from the user's preference; defaults per locale. */
    @Volatile
    var useEasternDigits: Boolean? = null

    fun easternByDefault(locale: Locale): Boolean = locale != Locale.ENGLISH

    fun format(value: Number, locale: Locale): String =
        localise(value.toString(), locale)

    fun localise(text: String, locale: Locale): String {
        val eastern = useEasternDigits ?: easternByDefault(locale)
        if (!eastern) return text
        return buildString(text.length) {
            for (ch in text) {
                append(if (ch in '0'..'9') EASTERN[ch - '0'] else ch)
            }
        }
    }

    /** Always Latin digits: used for phone numbers, plates and codes. */
    fun latin(text: String): String = buildString(text.length) {
        for (ch in text) {
            val index = EASTERN.indexOf(ch)
            append(if (index >= 0) ('0' + index) else ch)
        }
    }
}

object MoneyFormatter {

    /**
     * "۵۰۰ افغانی" or "500 AFN".
     *
     * The amount is derived from integer minor units; no float touches this
     * path, so a fare never renders as 449.99999.
     */
    /**
     * The same rendering, from the parts a server sends.
     *
     * Error contexts and notification payloads carry `<name>_minor` plus a
     * `currency` rather than a MoneyValue, and Strings needs to turn those into
     * a sentence without the caller building a domain object first.
     */
    fun format(amountMinor: Long, currency: String, strings: Strings): String =
        format(MoneyValue(amountMinor, currency), strings)

    fun format(money: MoneyValue, strings: Strings): String {
        val digits = minorDigits(money.currency)
        val negative = money.amountMinor < 0
        // The sign is applied here, not left to BigDecimal, so that the digits
        // are grouped and localised without it and the sign can be attached to
        // an isolated run -- see [signed].
        val magnitude = if (negative) -money.amountMinor else money.amountMinor
        val major = BigDecimal(magnitude).movePointLeft(digits)
        val plain =
            if (major.stripTrailingZeros().scale() <= 0) major.toBigInteger().toString()
            else major.stripTrailingZeros().toPlainString()

        val grouped = group(plain)
        val symbol = strings["common.label.currency_afn"]
        val number = Numerals.localise(grouped, strings.locale)
        return "${signed(number, negative = negative)} $symbol"
    }

    /**
     * A number with a sign that stays on the correct side of it.
     *
     * A leading "-" in front of Arabic-Indic digits inside a right-to-left
     * paragraph does not stay put. The digits are bidi class AN and the sign
     * is neutral against them, so the algorithm resolves it to the paragraph
     * direction and moves it to the other end: the driver's ledger rendered
     * `-۵۵ افغانی` as `۵۵- افغانی`, with the sign sitting between the number
     * and the currency. On a screen that exists to tell a driver what he owes,
     * a minus that has drifted off its number is not a typographic complaint.
     *
     * The isolate is what pins it. LRI..PDI makes the sign and the digits one
     * left-to-right run, which is how a signed number is read in Dari and
     * Pashto as well -- numbers are read left to right in both.
     *
     * Only signed numbers are wrapped. A positive amount has nothing that can
     * drift, and wrapping it would put two invisible characters into every
     * fare in the product for no gain.
     *
     * U+2212 rather than the ASCII hyphen: this is a minus, and the two were
     * already being used interchangeably on the same row of the same screen.
     */
    fun signed(number: String, negative: Boolean, showPlus: Boolean = false): String {
        val sign = when {
            negative -> "\u2212"
            showPlus -> "+"
            else -> return number
        }
        return "\u2066" + sign + number + "\u2069"
    }

    /** Thousands separators, applied to the integer part only. */
    private fun group(plain: String): String {
        val negative = plain.startsWith("-")
        val body = plain.removePrefix("-")
        val (whole, fraction) = body.split(".").let {
            it[0] to it.getOrNull(1)
        }
        val grouped = whole.reversed().chunked(3).joinToString(",").reversed()
        return buildString {
            if (negative) append("-")
            append(grouped)
            if (fraction != null) append(".").append(fraction)
        }
    }
}
