package af.velro.domain

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PlaceNamesTest {

    @Test
    fun `a village is found however its yeh and kaf were typed`() {
        // The compiled list and the passenger's keyboard rarely agree on these.
        assertTrue(PlaceNames.matches("خیشکی", "خيشكي"))
        assertTrue(PlaceNames.matches("ابراهیم‌خیل", "ابراهیم خیل"))
        assertTrue(PlaceNames.matches("ابراهیم‌خیل", "ابراهيمخيل"))
    }

    @Test
    fun `a partial name matches from anywhere in the word`() {
        assertTrue(PlaceNames.matches("تازه‌فرنجل", "فرنجل"))
        assertTrue(PlaceNames.matches("قلعه عظیم‌الله", "عظیم"))
    }

    @Test
    fun `an empty query matches everything, so the list starts whole`() {
        assertTrue(PlaceNames.matches("هر قریه", ""))
        assertTrue(PlaceNames.matches("هر قریه", "   "))
    }

    @Test
    fun `Pashto letters are not folded into their Persian lookalikes`() {
        // ږ and ز are different letters in different words. Folding them would
        // merge two villages that are not the same place.
        assertFalse(PlaceNames.matches("ږغ", "زغ"))
        assertFalse(PlaceNames.matches("ښکلی", "شکلی"))
    }

    @Test
    fun `unrelated names do not match`() {
        assertFalse(PlaceNames.matches("سیاه‌گرد", "شینواری"))
    }
}
