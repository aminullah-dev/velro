package af.velro.core.i18n

import af.velro.domain.Locale
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Money inside a sentence.
 *
 * The server sends amounts the only way a machine should: `<name>_minor` plus
 * a `currency` -- locale-free, exact, no floats. Three sentences spliced those
 * integers straight into prose, because substitution has no idea what a number
 * means:
 *
 *     "You need at least {minimum_minor} to request a payout."
 *
 * For a fifty-afghani minimum that read "You need at least 5000", with no
 * currency at all, to a driver deciding whether he has enough to ask for his
 * money. The other two were a debt and a driver's offered fare.
 */
class MoneyInSentencesTest {

    private fun dari(vararg pairs: Pair<String, String>) =
        Strings.of(Locale.DARI, mapOf("common.label.currency_afn" to "افغانی", *pairs))

    private fun english(vararg pairs: Pair<String, String>) =
        Strings.of(Locale.ENGLISH, mapOf("common.label.currency_afn" to "AFN", *pairs))

    @Test
    fun `a minor-unit amount becomes money, not a bigger number`() {
        val s = english("k" to "You need at least {amount} to request a payout.")
        val out = s["k", mapOf("minimum_minor" to 5000, "currency" to "AFN")]
        assertEquals("You need at least 50 AFN to request a payout.", out)
    }

    @Test
    fun `the named placeholder works as well as the generic one`() {
        val s = english("k" to "You owe {owed}; nothing to withdraw.")
        val out = s["k", mapOf("owed_minor" to 700, "currency" to "AFN")]
        assertEquals("You owe 7 AFN; nothing to withdraw.", out)
    }

    @Test
    fun `Dari gets Eastern numerals and its own currency word`() {
        val s = dari("k" to "یک راننده {amount} پیشنهاد داد.")
        val out = s["k", mapOf("amount_minor" to 65000, "currency" to "AFN")]
        assertEquals("یک راننده ۶۵۰ افغانی پیشنهاد داد.", out)
    }

    @Test
    fun `thousands are grouped`() {
        val s = english("k" to "{amount}")
        assertEquals("12,500 AFN", s["k", mapOf("amount_minor" to 1_250_000, "currency" to "AFN")])
    }

    @Test
    fun `a context with no currency is left exactly alone`() {
        // Not every _minor in a context is money the sentence wants rendered,
        // and without a currency there is nothing to render it as. Guessing a
        // currency here would turn "5000 metres" into "50 AFN".
        val s = english("k" to "{amount_minor}")
        assertEquals("5000", s["k", mapOf("amount_minor" to 5000)])
    }

    @Test
    fun `no currency means no amount placeholder is invented`() {
        val s = english("k" to "[{amount}]")
        assertEquals(
            "an amount must not be conjured from a context with no currency",
            "[{amount}]", s["k", mapOf("amount_minor" to 5000)],
        )
    }

    @Test
    fun `two amounts do not fight over which one is 'the' amount`() {
        // With more than one, `amount` is nobody's: whichever key happened to
        // iterate first would otherwise decide, and a sentence would silently
        // print the wrong figure depending on map ordering.
        val s = english("k" to "[{amount}]")
        val out = s["k", mapOf(
            "requested_minor" to 10_000, "available_minor" to 4_000, "currency" to "AFN",
        )]
        assertEquals(
            "an ambiguous amount must stay unresolved rather than pick one",
            "[{amount}]", out,
        )
    }

    @Test
    fun `a sentence that genuinely wants the integer can still have it`() {
        val s = english("k" to "code {amount_minor}")
        val out = s["k", mapOf("amount_minor" to 5000, "currency" to "AFN")]
        assertTrue("the raw placeholder must survive", out.contains("5000"))
    }

    @Test
    fun `two amounts in one sentence each render, and neither claims to be the amount`() {
        val s = english("k" to "{requested} of {available}")
        val out = s["k", mapOf(
            "requested_minor" to 10_000, "available_minor" to 4_000, "currency" to "AFN",
        )]
        assertEquals("100 AFN of 40 AFN", out)
    }

    @Test
    fun `an unknown key still returns the key rather than a blank`() {
        val s = english()
        assertEquals("nope.missing", s["nope.missing", mapOf("currency" to "AFN")])
    }
}
