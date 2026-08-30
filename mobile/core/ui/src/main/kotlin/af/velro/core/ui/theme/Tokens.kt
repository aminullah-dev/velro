package af.velro.core.ui.theme

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Design tokens.
 *
 * One set, shared with the admin panel. VELRO should read as premium, clean and
 * trustworthy: a deep green that is not a national flag, generous whitespace,
 * no decorative gradients, and no more than one accent on a screen.
 *
 * Contrast is checked against WCAG AA on every pair used for text, because a
 * driver reads this in daylight through a windscreen.
 */
object VelroColors {
    // Primary: a deep, calm green. Legible on white at any size, and distinct
    // from the yellows and reds already used by local taxi signage.
    val Green900 = Color(0xFF06301F)
    val Green800 = Color(0xFF0A4A30)
    val Green700 = Color(0xFF0E6042)
    val Green600 = Color(0xFF127954)
    val Green500 = Color(0xFF189669)
    val Green200 = Color(0xFF8FD9BC)
    val Green100 = Color(0xFFC7ECDC)
    val Green50 = Color(0xFFEAF7F1)

    // A single accent, used only where the eye must land: a seat count running
    // out, a fare, an emergency control.
    val Amber600 = Color(0xFFB45309)
    val Amber500 = Color(0xFFD97706)
    val Amber100 = Color(0xFFFEF3C7)

    val Red700 = Color(0xFFB42318)
    val Red500 = Color(0xFFD92D20)
    val Red100 = Color(0xFFFEE4E2)

    val Neutral900 = Color(0xFF101828)
    val Neutral700 = Color(0xFF344054)
    val Neutral500 = Color(0xFF667085)
    // The boundary of a control -- a field edge, a card outline.
    //
    // Measured, not chosen by eye: WCAG puts non-text contrast at 3:1 and the
    // old outline was Neutral300 at 1.47:1 against white. That is a border you
    // can see on a clean screen in a room, and cannot see on a cracked one in
    // Ghorband sunlight -- which is where somebody has to find the phone field
    // before they can sign in at all. 3.59:1.
    val Neutral400 = Color(0xFF7D8899)
    val Neutral300 = Color(0xFFD0D5DD)
    val Neutral200 = Color(0xFFE4E7EC)
    val Neutral100 = Color(0xFFF2F4F7)
    val Neutral50 = Color(0xFFF9FAFB)
    val White = Color(0xFFFFFFFF)

    // Dark surfaces, for a driver working after sunset.
    //
    // DarkBackground sits *under* DarkSurface rather than equal to it. Both
    // themes used one colour for the page and for the cards on it, so a card
    // was separated from its page by a one-pixel line and nothing else --
    // which is what made the product read as a wireframe rather than a
    // finished app. A card should be a surface lying on a ground.
    val DarkBackground = Color(0xFF0B0F14)
    val DarkSurface = Color(0xFF13181F)
    val DarkSurfaceRaised = Color(0xFF1B222C)
    val DarkOnSurface = Color(0xFFE7EBF0)
}

/** A 4dp grid. Every gap in the product is a multiple of it. */
object Spacing {
    val xxs: Dp = 2.dp
    val xs: Dp = 4.dp
    val sm: Dp = 8.dp
    val md: Dp = 12.dp
    val lg: Dp = 16.dp
    val xl: Dp = 24.dp
    val xxl: Dp = 32.dp
    val xxxl: Dp = 48.dp

    /** The screen gutter. Wide enough that Perso-Arabic descenders never clip. */
    val gutter: Dp = 20.dp
}

object Radius {
    val sm: Dp = 8.dp
    val md: Dp = 12.dp
    val lg: Dp = 16.dp
    val xl: Dp = 24.dp
    val pill: Dp = 999.dp

    /**
     * Cards and sheets.
     *
     * Softer than a control's radius on purpose, so a surface and a button
     * read as different kinds of thing without either being labelled.
     */
    val card: Dp = 20.dp
}

object Sizing {
    /**
     * The minimum touch target.
     *
     * 52dp rather than the 48dp minimum: this is used one-handed, in a moving
     * vehicle, often by someone wearing gloves in winter.
     */
    val touchTarget: Dp = 52.dp
    val buttonHeight: Dp = 56.dp
    val fieldHeight: Dp = 56.dp
    val iconSm: Dp = 18.dp
    val iconMd: Dp = 24.dp
    val iconLg: Dp = 32.dp
    val avatar: Dp = 44.dp
}

/**
 * Type scale.
 *
 * Perso-Arabic needs roughly 15-20% more line height than Latin at the same
 * size, so the ratios here are set per script rather than globally -- see
 * [Typography].
 */
object TypeScale {
    val displaySize = 32.sp
    val titleSize = 22.sp
    val headingSize = 18.sp
    val bodySize = 16.sp
    val labelSize = 14.sp
    val captionSize = 12.sp

    const val LATIN_LINE_RATIO = 1.35f
    const val PERSO_ARABIC_LINE_RATIO = 1.60f
}
