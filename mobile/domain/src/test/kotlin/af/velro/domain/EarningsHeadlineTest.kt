package af.velro.domain

import kotlin.math.abs
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The headline reads from the same place the label does.
 *
 * `owesPlatform` nets `pending` into `available`; the headline did not, and
 * showed raw `available` whenever the netted position said the money was his.
 * An ordinary shift breaks that: request a full payout, then complete one more
 * cash trip before the office marks the payout PAID. `available` is now the
 * commission on that trip, negative; `pending` is the payout, positive and
 * larger. The wallet as a whole is his, so the label said "available" -- and
 * the number under it was "-7 afghani" in the take-your-money green.
 */
class EarningsHeadlineTest {

    private fun wallet(available: Long, pending: Long = 0) = Earnings(
        available = MoneyValue(available, "AFN"),
        pending = MoneyValue(pending, "AFN"),
        lifetimeEarned = MoneyValue(6300, "AFN"),
        lifetimeCommission = MoneyValue(700, "AFN"),
        completedTrips = 1,
    )

    @Test
    fun `a cash trip after a payout request does not headline a negative`() {
        // The regression. A full payout of 5000 is in flight, then one more
        // cash trip leaves VELRO's 700 in his pocket.
        val midShift = wallet(available = -700, pending = 5000)
        assertFalse("he is still owed 4300 overall", midShift.owesPlatform)
        assertEquals(4300L, midShift.headlineAmount.amountMinor)
        assertTrue(
            "the raw available figure must never be the headline",
            midShift.headlineAmount.amountMinor >= 0,
        )
    }

    @Test
    fun `holding the platform's share is a debt`() {
        val owing = wallet(available = -700)
        assertTrue(owing.owesPlatform)
        assertEquals(700L, owing.headlineAmount.amountMinor)

        // A payout smaller than the debt does not flip it; it shrinks it.
        val partly = wallet(available = -700, pending = 500)
        assertTrue(partly.owesPlatform)
        assertEquals(200L, partly.headlineAmount.amountMinor)
    }

    @Test
    fun `an ordinary positive wallet headlines what is his`() {
        val plain = wallet(available = 5600)
        assertFalse(plain.owesPlatform)
        assertEquals(5600L, plain.headlineAmount.amountMinor)

        // A payout in flight is still his money, and the headline counts it
        // -- the same way owesPlatform does.
        val paying = wallet(available = 600, pending = 5000)
        assertFalse(paying.owesPlatform)
        assertEquals(5600L, paying.headlineAmount.amountMinor)
    }

    @Test
    fun `the headline is the netted position, whichever way it points`() {
        // Never one bucket under words that describe the other.
        for (e in listOf(
            wallet(-700, 5000), wallet(300, -1000), wallet(5600, 0),
            wallet(0, 5600), wallet(-700, 0), wallet(0, 0),
        )) {
            assertEquals(
                "wallet(${e.available.amountMinor}, ${e.pending.amountMinor})",
                abs(e.owed.amountMinor),
                e.headlineAmount.amountMinor,
            )
        }
    }

    @Test
    fun `the currency travels with the netted amount`() {
        assertEquals("AFN", wallet(-700, 5000).headlineAmount.currency)
        assertEquals("AFN", wallet(-700, 0).headlineAmount.currency)
    }
}
