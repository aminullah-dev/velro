package af.velro.core.ui.theme

import android.provider.Settings
import androidx.compose.animation.AnimatedContentTransitionScope
import androidx.compose.animation.EnterTransition
import androidx.compose.animation.ExitTransition
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.runtime.Composable
import androidx.compose.runtime.ProvidableCompositionLocal
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext

/**
 * Motion.
 *
 * The product had none. Not "a little" -- a search of both apps for
 * `animate*AsState`, `AnimatedVisibility`, `AnimatedContent` and a navigation
 * transition returned nothing, so every screen replaced the last as a jump
 * cut and the seven-step booking form cut seven times between a passenger
 * choosing a district and seeing a fare. Correct, and it reads as a slideshow
 * of a product rather than a product.
 *
 * Two durations, not a scale of them. A screen arriving is [SCREEN_MS]; a
 * piece of one changing is [WITHIN_MS], faster because the eye is already
 * there and does not have to be led. Anything slower than this on a 2019
 * handset stops reading as polish and starts reading as lag.
 */
object Motion {
    /** A whole screen arriving or leaving. */
    const val SCREEN_MS = 280

    /** A region inside a screen changing -- a step, a chip row, a value. */
    const val WITHIN_MS = 200

    /**
     * The curve. Fast to leave, slow to settle: motion that decelerates reads
     * as a thing coming to rest, and motion at a constant speed reads as a
     * machine moving it.
     */
    val easing = FastOutSlowInEasing
}

/**
 * Whether animation should play at all.
 *
 * Android lets a person turn animation off system-wide, and on the handsets
 * this product is for that switch is not hypothetical -- it is one of the
 * first things people reach for on a slow phone, alongside developer options,
 * and some vendor "battery saver" modes set it without asking. Honouring it
 * costs one read and means the app never spends frames a person has already
 * said they do not want.
 *
 * Also the reason the value is a CompositionLocal rather than a direct read:
 * a test or a preview can force it either way without a device setting.
 */
val LocalAnimationsEnabled: ProvidableCompositionLocal<Boolean> =
    compositionLocalOf { true }

/** Reads the system animator scale. 0 means the person has turned animation off. */
@Composable
fun systemAnimationsEnabled(): Boolean {
    val context = LocalContext.current
    return remember(context) {
        Settings.Global.getFloat(
            context.contentResolver,
            Settings.Global.ANIMATOR_DURATION_SCALE,
            1f,
        ) != 0f
    }
}

/**
 * The navigation transitions, shared by both apps.
 *
 * `SlideDirection.Start` and `.End` are layout-aware, unlike `.Left`/`.Right`:
 * a forward push travels right-to-left in English and left-to-right in Dari
 * and Pashto without a second set of specifications. Getting this wrong is not
 * cosmetic -- a back gesture whose animation runs the wrong way tells an RTL
 * reader they went forward.
 *
 * Slide *and* fade rather than slide alone. A bare slide on a low-refresh
 * panel shows its steps; the fade covers them for the cost of one more
 * animated property.
 */
object NavMotion {
    private val spec = tween<Float>(Motion.SCREEN_MS, easing = Motion.easing)
    private val offsetSpec =
        tween<androidx.compose.ui.unit.IntOffset>(Motion.SCREEN_MS, easing = Motion.easing)

    fun enter(scope: AnimatedContentTransitionScope<*>, animate: Boolean): EnterTransition =
        if (!animate) EnterTransition.None else with(scope) {
            slideIntoContainer(
                AnimatedContentTransitionScope.SlideDirection.Start,
                animationSpec = offsetSpec,
            ) + fadeIn(spec)
        }

    fun exit(scope: AnimatedContentTransitionScope<*>, animate: Boolean): ExitTransition =
        if (!animate) ExitTransition.None else with(scope) {
            slideOutOfContainer(
                AnimatedContentTransitionScope.SlideDirection.Start,
                animationSpec = offsetSpec,
            ) + fadeOut(spec)
        }

    fun popEnter(scope: AnimatedContentTransitionScope<*>, animate: Boolean): EnterTransition =
        if (!animate) EnterTransition.None else with(scope) {
            slideIntoContainer(
                AnimatedContentTransitionScope.SlideDirection.End,
                animationSpec = offsetSpec,
            ) + fadeIn(spec)
        }

    fun popExit(scope: AnimatedContentTransitionScope<*>, animate: Boolean): ExitTransition =
        if (!animate) ExitTransition.None else with(scope) {
            slideOutOfContainer(
                AnimatedContentTransitionScope.SlideDirection.End,
                animationSpec = offsetSpec,
            ) + fadeOut(spec)
        }
}
