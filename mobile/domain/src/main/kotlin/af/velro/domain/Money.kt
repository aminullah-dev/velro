package af.velro.domain

import java.math.BigDecimal
import java.math.RoundingMode

/**
 * Money.
 *
 * Integer minor units plus an ISO-4217 code, exactly as the server stores and
 * transmits it. Doubles are absent from this file on purpose: a fare that
 * renders as 449.99999 AFN on a phone is a support call.
 *
 * Arithmetic between different currencies throws. There is no implicit
 * conversion, ever.
 */
/** An amount and the currency it is in. There is no other money type. */
data class MoneyValue(
    val amountMinor: Long,
    val currency: String = DEFAULT_CURRENCY,
) : Comparable<MoneyValue> {

    init {
        require(currency.length == 3) { "currency must be an ISO-4217 code" }
    }

    operator fun plus(other: MoneyValue): MoneyValue {
        requireSameCurrency(other)
        return copy(amountMinor = amountMinor + other.amountMinor)
    }

    operator fun minus(other: MoneyValue): MoneyValue {
        requireSameCurrency(other)
        return copy(amountMinor = amountMinor - other.amountMinor)
    }

    operator fun times(factor: Int): MoneyValue = copy(amountMinor = amountMinor * factor)

    override fun compareTo(other: MoneyValue): Int {
        requireSameCurrency(other)
        return amountMinor.compareTo(other.amountMinor)
    }

    val isZero: Boolean get() = amountMinor == 0L
    val isNegative: Boolean get() = amountMinor < 0L

    /**
     * A share of this amount in basis points (1000 bp = 10%), ROUND_HALF_UP.
     *
     * Stated explicitly and matched against the server's table in
     * `docs/domain/lifecycles.json`: a commission that rounds differently in the
     * app and on the server loses a driver one afghani at a time, and they will
     * notice.
     */
    fun percentage(basisPoints: Int): MoneyValue {
        require(basisPoints in 0..10_000) { "basisPoints must be between 0 and 10000" }
        val share = BigDecimal(amountMinor)
            .multiply(BigDecimal(basisPoints))
            .divide(BigDecimal(10_000), 0, RoundingMode.HALF_UP)
        return copy(amountMinor = share.toLong())
    }

    /** Splits into (share, remainder). The two always sum back to this exactly. */
    fun splitOff(basisPoints: Int): Pair<MoneyValue, MoneyValue> {
        val share = percentage(basisPoints)
        return share to (this - share)
    }

    /** For formatters only. Never for arithmetic, never for storage. */
    fun toMajor(): BigDecimal =
        BigDecimal(amountMinor).movePointLeft(minorDigits(currency))

    private fun requireSameCurrency(other: MoneyValue) {
        if (currency != other.currency) {
            throw CurrencyMismatchException(currency, other.currency)
        }
    }

    companion object {
        fun zero(currency: String = DEFAULT_CURRENCY) = MoneyValue(0, currency)
    }
}

class CurrencyMismatchException(left: String, right: String) :
    IllegalArgumentException("cannot combine $left and $right")

const val DEFAULT_CURRENCY = "AFN"

private val MINOR_DIGITS = mapOf("AFN" to 2, "USD" to 2, "EUR" to 2, "PKR" to 2)

fun minorDigits(currency: String): Int = MINOR_DIGITS[currency] ?: 2

/** How a fare divides between the driver and VELRO. */
data class CommissionSplit(
    val gross: MoneyValue,
    val platform: MoneyValue,
    val driver: MoneyValue,
    val rateBasisPoints: Int,
) {
    init {
        check(platform + driver == gross) { "a commission split must close exactly" }
    }

    companion object {
        fun of(gross: MoneyValue, rateBasisPoints: Int): CommissionSplit {
            val (platform, driver) = gross.splitOff(rateBasisPoints)
            return CommissionSplit(gross, platform, driver, rateBasisPoints)
        }
    }
}
