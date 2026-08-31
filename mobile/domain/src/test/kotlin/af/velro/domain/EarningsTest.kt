package af.velro.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Which way the money is pointing.
 *
 * VELRO's fares are cash, handed over at the vehicle, so the ordinary state of
 * a working driver's wallet is negative: he has the whole fare in his pocket
 * and the platform's share is inside it. "How much do I have" and "how much do
 * I owe" are the same number with a sign, and the sign must never reach the
 * screen -- the words do that.
 *
 * The trap this pins down: requesting a settlement moves the debt out of
 * `available` and into `pending`. A rule written against `available` alone
 * therefore reports "you owe nothing" at the exact moment the driver acts on
 * the debt. The home card did, while the earnings screen one tap behind it
 * still showed the money, so the two screens disagreed about a man's own
 * wallet.
 */
class EarningsTest {

    private fun wallet(available: Long, pending: Long = 0) = Earnings(
        available = MoneyValue(available, "AFN"),
        pending = MoneyValue(pending, "AFN"),
        lifetimeEarned = MoneyValue(6300, "AFN"),
        lifetimeCommission = MoneyValue(700, "AFN"),
        completedTrips = 1,
    )

    @Test
    fun `a driver holding the platform's share owes it`() {
        assertTrue(wallet(available = -700).owesPlatform)
        assertEquals(700L, wallet(available = -700).headlineAmount.amountMinor)
    }

    @Test
    fun `opening a settlement does not clear the debt`() {
        // The regression. available returns to zero and the seven moves to
        // pending; the driver still owes exactly seven afghani.
        val settling = wallet(available = 0, pending = -700)
        assertTrue("the debt only changed bucket", settling.owesPlatform)
        assertEquals(700L, settling.headlineAmount.amountMinor)
    }

    @Test
    fun `a payout in flight is not a debt`() {
        // The mirror case: positive pending is money coming to him.
        val paying = wallet(available = 0, pending = 5600)
        assertFalse(paying.owesPlatform)
    }

    @Test
    fun `an empty wallet owes nothing`() {
        assertFalse(wallet(available = 0).owesPlatform)
        assertEquals(0L, wallet(available = 0).headlineAmount.amountMinor)
    }

    @Test
    fun `the headline is never negative, whichever way it points`() {
        // The sign is carried by the label, not by the number: a driver should
        // never be shown "-7 afghani" and left to work out whose it is.
        for (e in listOf(
            wallet(-700), wallet(0, -700), wallet(5600), wallet(0, 5600), wallet(0)
        )) {
            assertTrue(
                "headline ${e.headlineAmount.amountMinor} must not be negative",
                e.headlineAmount.amountMinor >= 0,
            )
        }
    }

    @Test
    fun `a debt larger than the free balance still nets out`() {
        // Part paid, part still owed.
        val mixed = wallet(available = 300, pending = -1000)
        assertTrue(mixed.owesPlatform)
        assertEquals(700L, mixed.headlineAmount.amountMinor)
    }
}
