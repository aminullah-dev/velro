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
        val major = BigDecimal(money.amountMinor).movePointLeft(digits)
        val plain =
            if (major.stripTrailingZeros().scale() <= 0) major.toBigInteger().toString()
            else major.stripTrailingZeros().toPlainString()

        val grouped = group(plain)
        val symbol = strings["common.label.currency_afn"]
        return "${Numerals.localise(grouped, strings.locale)} $symbol"
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
