package af.velro.core.ui

import af.velro.core.ui.theme.Sizing
import af.velro.core.ui.theme.Spacing
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The size relationships the layout quietly depends on.
 *
 * Five call sites used to carry `Modifier.heightIn(min = 52.dp)` with comments
 * claiming it guaranteed the touch target on the taps that cost money. It
 * guaranteed nothing -- the buttons were already 56dp -- and it was a literal,
 * so if `buttonHeight` were ever lowered the "52dp guarantee" would have gone
 * on reading as true in the comments while being false on the glass. The
 * literals are gone; this is the thing that was actually being claimed.
 */
class SizingTest {

    @Test
    fun `a button is at least a touch target tall`() {
        assertTrue(
            "buttonHeight ${Sizing.buttonHeight} is under the ${Sizing.touchTarget} " +
                "minimum, so every PrimaryAction is now too small to hit reliably",
            Sizing.buttonHeight >= Sizing.touchTarget,
        )
    }

    @Test
    fun `a text field is at least a touch target tall`() {
        assertTrue(
            "fieldHeight ${Sizing.fieldHeight} is under ${Sizing.touchTarget}",
            Sizing.fieldHeight >= Sizing.touchTarget,
        )
    }

    @Test
    fun `the touch target clears the platform minimum with room for gloves`() {
        // 48dp is Android's floor. VELRO sits above it on purpose: this is
        // used one-handed, in a moving vehicle, in a Ghorband winter.
        assertTrue(
            "touchTarget ${Sizing.touchTarget} must stay above the 48dp platform floor",
            Sizing.touchTarget.value >= 48f,
        )
    }

    @Test
    fun `the spacing scale stays on its own grid`() {
        // Every gap is a multiple of 4dp except the documented half-step. A
        // stray 5 or 7 makes two screens that were meant to match disagree by
        // a pixel nobody can find later.
        assertTrue(
            "xxs is the one half-step and must stay half of xs",
            Spacing.xxs.value * 2 == Spacing.xs.value,
        )
        val scale = listOf(
            "xs" to Spacing.xs, "sm" to Spacing.sm,
            "md" to Spacing.md, "lg" to Spacing.lg, "xl" to Spacing.xl,
            "xxl" to Spacing.xxl, "xxxl" to Spacing.xxxl,
            "gutter" to Spacing.gutter,
        )
        for ((name, dp) in scale) {
            assertTrue(
                "Spacing.$name is $dp, which is not a multiple of 4dp",
                dp.value.toInt() % 4 == 0 && dp.value == dp.value.toInt().toFloat(),
            )
        }
    }
}
