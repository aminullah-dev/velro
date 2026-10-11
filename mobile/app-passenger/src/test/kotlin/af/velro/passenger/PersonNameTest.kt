package af.velro.passenger

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The two-part name the passenger app requires, and the one string the server
 * keeps. Split and join have to agree, or the account screen would show a
 * passenger a different name from the one she gave.
 */
class PersonNameTest {

    @Test
    fun `both parts are trimmed and joined with one space`() {
        assertEquals("احمد شاه رحیمی", PersonName.join("  احمد ", " شاه   رحیمی "))
    }

    @Test
    fun `the first word is the first name and the rest is the last name`() {
        assertEquals("احمد" to "شاه رحیمی", PersonName.split("احمد شاه رحیمی"))
    }

    @Test
    fun `a missing name splits into two blanks and a single word into a first name`() {
        assertEquals("" to "", PersonName.split(null))
        assertEquals("" to "", PersonName.split("   "))
        assertEquals("احمد" to "", PersonName.split("احمد"))
    }

    @Test
    fun `split then join gives back the stored name`() {
        val stored = "Mohammad Nabi Karimi"
        val (first, last) = PersonName.split(stored)
        assertEquals(stored, PersonName.join(first, last))
    }

    @Test
    fun `each part needs two letters after trimming`() {
        assertTrue(PersonName.isValid("نجیب", "احمدی"))
        assertFalse("an initial is not a name", PersonName.isValid("ن", "احمدی"))
        assertFalse("spaces do not count", PersonName.isValid("نجیب", "  ا  "))
        assertFalse("both are required", PersonName.isValid("نجیب", ""))
    }
}
