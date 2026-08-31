package af.velro.core.i18n

import af.velro.domain.MoneyValue
import af.velro.domain.Locale
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The sign on a negative amount, and where it ends up.
 *
 * A leading "-" in front of Arabic-Indic digits inside a right-to-left
 * paragraph does not stay put: the digits are bidi class AN, the sign is
 * neutral against them, and the algorithm resolves it to the paragraph
 * direction and moves it to the far end of the number. The driver's ledger
 * rendered a 55-afghani deduction with the minus between the number and the
 * word "افغانی".
 *
 * The fix is a pair of invisible characters, which is exactly why it needs a
 * test: nothing about the screen looks different when they are dropped, and
 * the next person to touch this file has no way to see them.
 */
class SignedMoneyTest {

    private fun dari() =
        Strings.of(Locale.DARI, mapOf("common.label.currency_afn" to "افغانی"))

    private val LRI = '⁦'
    private val PDI = '⁩'
    private val MINUS = '−'

    @Test
    fun `a negative amount keeps its sign in an isolate`() {
        val out = MoneyFormatter.format(MoneyValue(-5500, "AFN"), dari())
        assertTrue("the run must be isolated", out.contains(LRI) && out.contains(PDI))
        assertTrue("a real minus, not a hyphen", out.contains(MINUS))
        assertFalse("the ASCII hyphen must not survive", out.contains('-'))
        // The sign belongs to the number, so nothing may separate them.
        assertTrue(
            "sign must sit immediately before the digits",
            out.contains("$LRI$MINUS"),
        )
    }

    @Test
    fun `a positive amount is left alone`() {
        val out = MoneyFormatter.format(MoneyValue(5500, "AFN"), dari())
        assertEquals("۵۵ افغانی", out)
        assertFalse(
            "a positive number has no sign to drift, so it carries no isolate",
            out.contains(LRI) || out.contains(PDI),
        )
    }

    @Test
    fun `zero is not negative`() {
        val out = MoneyFormatter.format(MoneyValue(0, "AFN"), dari())
        assertEquals("۰ افغانی", out)
        assertFalse(out.contains(MINUS))
    }

    @Test
    fun `the magnitude is unchanged by the sign`() {
        val negative = MoneyFormatter.format(MoneyValue(-125_000, "AFN"), dari())
        val positive = MoneyFormatter.format(MoneyValue(125_000, "AFN"), dari())
        assertTrue(
            "both must render the same digits, grouped the same way",
            negative.contains("۱,۲۵۰") && positive.contains("۱,۲۵۰"),
        )
    }

    @Test
    fun `an explicit plus is isolated too`() {
        // The ledger marks credits with a "+". Concatenated onto an already
        // formatted string it sits outside any isolate and drifts exactly as
        // the minus did, so it goes through the same helper.
        val out = MoneyFormatter.signed("۲۵۰ افغانی", negative = false, showPlus = true)
        assertTrue(out.startsWith("$LRI+"))
        assertTrue(out.endsWith("$PDI"))
    }

    @Test
    fun `an unsigned call adds nothing`() {
        val out = MoneyFormatter.signed("۲۵۰ افغانی", negative = false)
        assertEquals("۲۵۰ افغانی", out)
    }
}
