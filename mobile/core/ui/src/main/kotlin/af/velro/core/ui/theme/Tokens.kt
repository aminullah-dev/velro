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

    // Containers for after dark.
    //
    // The status chips carried one hardcoded light pair each -- Neutral100,
    // Green50, Amber100, Red100 -- so on a dark card they were near-white
    // pills at 16:1 against their own background. A driver checking a trip at
    // night got a row of glowing tablets where the light theme has a quiet
    // label. These are their counterparts, each measured against the dark
    // card, not chosen by eye.
    val DarkGreenContainer = Color(0xFF0A4A30)
    val DarkAmberContainer = Color(0xFF4A2B06)
    val DarkRedContainer = Color(0xFF4C1512)
    // The muted foreground for a finished or cancelled status after dark.
    // Neutral400 measured 4.46:1 here -- close enough to pass by eye and not
    // close enough to pass, on the label that tells somebody their trip is
    // over. 4.82:1, still visibly dimmer than the live tones beside it.
    val Neutral350 = Color(0xFF828EA0)
    // The label on a disabled control. Material's own disabled treatment is
    // onSurface at 38% over onSurface at 12%, which measures 2.31:1 -- a
    // button that is simply not there in Ghorband sunlight, so a person cannot
    // tell whether the app is broken or their form is unfinished. 4.70:1,
    // still visibly quieter than the 7.58:1 of a live one.
    val Neutral550 = Color(0xFF5B6675)
    val Amber200 = Color(0xFFFCCF7A)
    // The error sentence after dark. Red500 is 3.69:1 on the dark card -- the
    // one pair the dark contrast test did not measure, on the line that
    // explains why something just failed. 9.18:1.
    val Red200 = Color(0xFFFDA29B)
    val DarkSurfaceRaised = Color(0xFF1B222C)
    val DarkOnSurface = Color(0xFFE7EBF0)

    /**
     * The brand field, and what sits on it.
     *
     * Deliberately constant across themes, unlike every other colour here.
     * The header used `colorScheme.primary`, which is the deep green in light
     * mode and the pale mint Green200 in dark -- so after dark the top of both
     * home screens inverted into the brightest block on the display, and the
     * status-bar icons the header forces light sat on it at 1.64:1. A brand
     * field is identity, not semantics: it is the same green on a white page
     * and a black one, the way a signboard is the same colour at noon and at
     * night. White on it measures 7.58:1 either way.
     */
    val BrandField = Green700
    val OnBrandField = White
}

/**
 * A 4dp grid, with one deliberate half-step.
 *
 * `xxs` is 2dp: the gap between a label and the value directly under it, where
 * a full step reads as a separation rather than a pairing. Everything else is
 * a multiple of 4, and SizingTest holds that -- the previous version of this
 * comment claimed every gap was, which was not true of the token immediately
 * below it.
 */
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
     * Cards and sheets, as the admin panel still draws them.
     *
     * The apps moved to [surface] with the soft redesign; this stays at its
     * value because the panel reads the same set and has not moved yet.
     */
    val card: Dp = 20.dp

    /**
     * Every card in the apps, after the soft redesign.
     *
     * Larger than [card] and well short of a pill, so a surface still reads as
     * a different kind of thing from a button -- which is now fully round --
     * without either being labelled. The same value as [xl], named separately
     * so a card and a corner that merely happens to be 24 can drift apart.
     */
    val surface: Dp = 24.dp

    /**
     * The top corners of a sheet that rides up over a map.
     *
     * Rounder than a card because it is a bigger thing: a panel the width of
     * the display with 24dp corners reads as a card that grew, and the point
     * is that it is the ground the rest of the screen lies on.
     */
    val sheet: Dp = 32.dp
}

/**
 * How far a surface sits above the one under it.
 *
 * Soft and diffuse rather than a hard edge: the redesign takes the hairline
 * off a white card on the light page and lets a wide, faint shadow say where
 * it ends. Only a few steps, so two cards on one screen cannot disagree about
 * how high they float.
 *
 * These are elevations, not darkness. How dark a shadow lands is decided in
 * `softShadow`, which also tones them down on Android 8 and older, where the
 * platform ignores a shadow's colour and draws every one at full strength.
 */
object Elevation {
    /** A card lying on the page. */
    val card: Dp = 10.dp

    /** A control floating over a map: the round buttons, the help pill. */
    val floating: Dp = 12.dp

    /** The filled primary button, whose shadow is tinted with its own green. */
    val button: Dp = 12.dp

    /** A sheet over the map, casting upward. */
    val sheet: Dp = 20.dp
}

/**
 * Frosted glass: how much of the surface colour a floating control keeps.
 *
 * The owner's direction for the redesign was "soft, glassy, almost minimal".
 * The controls that float over the map -- the round buttons, the help pill,
 * the drawer, the sheet -- are the surface colour at
 * these opacities rather than opaque white slabs, so the map reads through
 * them faintly. Not a blur: a backdrop blur on Android needs a library or API
 * 31, and a cheap handset pays for it on every frame the map is on screen.
 * Translucency, a white hairline and a faint shadow give the same impression
 * for nothing.
 *
 * Opaque enough that text on them keeps its contrast whatever is underneath;
 * ContrastTest measures the text pairs against the darkest ground the drawn
 * map can put behind them, composited at these values, not against white.
 */
object Glass {
    /** The round buttons, the help pill and the "Where to?" bar. */
    const val FLOATING = 0.82f

    /** The sheet: long text sits on it, so it is denser than a button. */
    const val PANEL = 0.90f

    /**
     * The drawer, densest of all. It lies over the whole of home -- text,
     * buttons and all, not only the map -- and at the sheet's opacity the
     * screen underneath read through as a second, ghostly page.
     */
    const val DRAWER = 0.96f

    /** The white rim that catches the light at the edge of the glass. */
    const val RIM_LIGHT = 0.70f

    /** The same rim after dark, where a bright edge would glare. */
    const val RIM_DARK = 0.10f
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

    /**
     * A document preview on the driver's papers screen.
     *
     * Tall enough to tell a licence from an identity card at a glance and to
     * see whether a thumb covered the lens -- which is the whole reason it is
     * there -- without pushing the status and the re-send button off a small
     * screen.
     */
    val thumbnail: Dp = 96.dp

    /**
     * The driver's own photograph on his profile.
     *
     * Large enough to be a portrait rather than a list avatar -- this is the
     * one screen where the point is that it is him.
     */
    val profilePhoto: Dp = 112.dp
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
    // Between display and title. Every fare on every screen is drawn at this
    // size, and until the theme defined it they were all drawn by the system
    // font instead of the bundled one.
    val headlineSize = 28.sp
    val subheadlineSize = 24.sp
    val titleSize = 22.sp
    val headingSize = 18.sp
    val bodySize = 16.sp
    val labelSize = 14.sp
    val captionSize = 12.sp

    const val LATIN_LINE_RATIO = 1.35f
    const val PERSO_ARABIC_LINE_RATIO = 1.60f
}
