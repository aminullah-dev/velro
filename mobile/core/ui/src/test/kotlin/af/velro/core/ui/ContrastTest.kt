package af.velro.core.ui

import af.velro.core.ui.theme.VelroColors
import androidx.compose.ui.graphics.Color
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Every colour pair the product actually puts on screen, measured.
 *
 * VELRO is read in a parked Corolla in Ghorband sunlight, often on a screen
 * with a crack across it. "Looks fine on the laptop" is not evidence about
 * that, and the difference between a 4.9:1 pair and a 3.2:1 pair is invisible
 * in Android Studio and decisive on a windscreen.
 *
 * This caught two real failures the day it was written: `outline` was 1.47:1
 * against white in light mode and 1.70:1 in dark, which is the border of every
 * text field and card in both apps. Somebody who cannot see the edge of the
 * phone field cannot sign in.
 */
class ContrastTest {

    /** WCAG 2.x relative luminance. */
    private fun luminance(color: Color): Double {
        fun channel(v: Float): Double {
            val c = v.toDouble()
            return if (c <= 0.03928) c / 12.92 else Math.pow((c + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * channel(color.red) +
            0.7152 * channel(color.green) +
            0.0722 * channel(color.blue)
    }

    private fun ratio(a: Color, b: Color): Double {
        val (hi, lo) = luminance(a).let { la ->
            luminance(b).let { lb -> maxOf(la, lb) to minOf(la, lb) }
        }
        return (hi + 0.05) / (lo + 0.05)
    }

    private fun assertContrast(name: String, fg: Color, bg: Color, minimum: Double) {
        val measured = ratio(fg, bg)
        assertTrue(
            "$name is ${"%.2f".format(measured)}:1 and must be at least $minimum:1",
            measured >= minimum,
        )
    }

    // 4.5:1 for normal text, 3:1 for large text and for anything non-text that
    // carries meaning -- a control's boundary, an icon that is the only label.
    private val TEXT = 4.5
    private val NON_TEXT = 3.0

    @Test
    fun `light mode text is readable`() {
        val white = VelroColors.White
        assertContrast("body on white", VelroColors.Neutral700, white, TEXT)
        assertContrast("heading on white", VelroColors.Neutral900, white, TEXT)
        assertContrast("muted on white", VelroColors.Neutral500, white, TEXT)
        assertContrast("primary green on white", VelroColors.Green700, white, TEXT)
        assertContrast("white on primary green", white, VelroColors.Green700, TEXT)
        assertContrast("error on white", VelroColors.Red700, white, TEXT)
        assertContrast("accent on white", VelroColors.Amber600, white, TEXT)
    }

    @Test
    fun `light mode text is readable on the page itself, not only on a card`() {
        // The page ground is Neutral50 and the cards on it are white, so every
        // pair above is really two pairs. Section headings, empty states and
        // helper text sit on the ground, and the ground is the darker of the
        // two -- measuring only against white would pass a pairing that fails
        // where the text actually is.
        val ground = VelroColors.Neutral50
        assertContrast("body on the page", VelroColors.Neutral700, ground, TEXT)
        assertContrast("heading on the page", VelroColors.Neutral900, ground, TEXT)
        assertContrast("muted on the page", VelroColors.Neutral500, ground, TEXT)
        assertContrast("primary green on the page", VelroColors.Green700, ground, TEXT)
        assertContrast("accent on the page", VelroColors.Amber600, ground, TEXT)
    }

    @Test
    fun `a card is distinguishable from the page under it`() {
        // Not a legibility threshold -- a card is not text -- but the whole
        // point of the change that introduced it. If these two ever collapse
        // to the same colour again the product goes back to being a wireframe
        // held together by hairlines, and nothing else would catch it.
        val separation = ratio(VelroColors.White, VelroColors.Neutral50)
        assertTrue(
            "a white card must not be the same colour as the page it lies on",
            separation > 1.0,
        )
        val dark = ratio(VelroColors.DarkSurface, VelroColors.DarkBackground)
        assertTrue("and the same after dark, where a shadow shows nothing", dark > 1.0)
    }

    @Test
    fun `light mode control boundaries are visible`() {
        // The failure this whole file exists for. Neutral300 sat here at
        // 1.47:1 -- a field edge that disappears in daylight.
        assertContrast(
            "outline on white", VelroColors.Neutral400, VelroColors.White, NON_TEXT
        )
    }

    @Test
    fun `dark mode text is readable`() {
        val surface = VelroColors.DarkSurface
        assertContrast("body on dark", VelroColors.DarkOnSurface, surface, TEXT)
        assertContrast("muted on dark", VelroColors.Neutral300, surface, TEXT)
        assertContrast("primary on dark", VelroColors.Green200, surface, TEXT)
        assertContrast("accent on dark", VelroColors.Amber500, surface, TEXT)
    }

    @Test
    fun `dark mode control boundaries are visible`() {
        assertContrast(
            "outline on dark", VelroColors.Neutral500, VelroColors.DarkSurface, NON_TEXT
        )
    }

    @Test
    fun `every status chip is legible in both themes`() {
        // Ten pairs, one per tone per theme. These were five light pairs used
        // in both, so after dark a booking card carried near-white pills at
        // 16:1 against it -- and the scarce-seat line sat at 3.55:1, under the
        // threshold, on the one sentence written to make somebody act.
        val light = listOf(
            Triple("neutral", VelroColors.Neutral700, VelroColors.Neutral100),
            Triple("active", VelroColors.Green700, VelroColors.Green50),
            Triple("attention", VelroColors.Amber600, VelroColors.Amber100),
            Triple("ended", VelroColors.Neutral500, VelroColors.Neutral100),
            Triple("failed", VelroColors.Red700, VelroColors.Red100),
        )
        val dark = listOf(
            Triple("neutral", VelroColors.Neutral300, VelroColors.DarkSurfaceRaised),
            Triple("active", VelroColors.Green200, VelroColors.DarkGreenContainer),
            Triple("attention", VelroColors.Amber200, VelroColors.DarkAmberContainer),
            Triple("ended", VelroColors.Neutral350, VelroColors.DarkSurfaceRaised),
            Triple("failed", VelroColors.Red200, VelroColors.DarkRedContainer),
        )
        for ((name, fg, bg) in light) {
            assertContrast("light $name chip", fg, bg, TEXT)
        }
        for ((name, fg, bg) in dark) {
            assertContrast("dark $name chip", fg, bg, TEXT)
        }
    }

    @Test
    fun `the brand field is legible and stays constant across themes`() {
        // The header ran on colorScheme.primary, which is the deep green in
        // light mode and pale mint in dark -- so after dark the top of both
        // home screens became the brightest block on the display, and the
        // light status-bar icons the header forces sat on it at 1.64:1. A
        // brand field is identity: the same green on a white page and a black
        // one.
        assertContrast(
            "header text on the brand field",
            VelroColors.OnBrandField, VelroColors.BrandField, TEXT,
        )
        // The action inside it inverts the same two colours and no others.
        assertContrast(
            "the header's action label",
            VelroColors.BrandField, VelroColors.OnBrandField, TEXT,
        )
        // Status-bar icons are forced light while the header is on screen, so
        // the field owes them non-text contrast too.
        assertContrast(
            "status-bar icons on the brand field",
            VelroColors.OnBrandField, VelroColors.BrandField, NON_TEXT,
        )
        assertTrue(
            "the brand field must not follow the scheme's primary, which inverts",
            VelroColors.BrandField != VelroColors.Green200,
        )
    }

    @Test
    fun `a chip does not glare off the card it sits on`() {
        // Not a legibility rule -- a chip is a label, not a control boundary.
        // It is a "does this belong to the same product" rule: a container
        // sixteen times brighter than its own card is a lamp, not a status.
        val dark = listOf(
            VelroColors.DarkSurfaceRaised,
            VelroColors.DarkGreenContainer,
            VelroColors.DarkAmberContainer,
            VelroColors.DarkRedContainer,
        )
        for (container in dark) {
            val measured = ratio(container, VelroColors.DarkSurface)
            assertTrue(
                "a dark chip container is ${"%.2f".format(measured)}:1 against " +
                    "its card and must stay under 3:1",
                measured < 3.0,
            )
        }
    }

    @Test
    fun `the scarce-seat warning is readable in both themes`() {
        // Amber600 direct from the palette was 3.55:1 on the dark card. The
        // scheme's secondary is Amber600 in light and Amber500 in dark, which
        // is the whole reason the scheme has the role.
        assertContrast("scarce seats, light", VelroColors.Amber600, VelroColors.White, TEXT)
        assertContrast(
            "scarce seats, dark", VelroColors.Amber500, VelroColors.DarkSurface, TEXT
        )
    }

    @Test
    fun `the amber accent is never used as light-mode text at its brightest`() {
        """
        Amber500 is 3.19:1 on white -- fine on the dark surface, not fine as
        light-mode text. The light scheme maps `secondary` to Amber600 for
        exactly that reason, and this test is what stops somebody swapping
        them back because the brighter one looks nicer in the palette.
        """
        assertTrue(
            "Amber500 must stay below the light-mode text threshold, so nobody " +
                "reaches for it there by mistake",
            ratio(VelroColors.Amber500, VelroColors.White) < TEXT,
        )
        assertContrast("Amber600 on white", VelroColors.Amber600, VelroColors.White, TEXT)
    }
}
