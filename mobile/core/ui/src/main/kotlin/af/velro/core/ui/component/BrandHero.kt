package af.velro.core.ui.component

import af.velro.core.ui.theme.Radius
import af.velro.core.ui.theme.Spacing
import af.velro.core.ui.theme.VelroColors
import android.app.Activity
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.heightIn
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.view.WindowCompat

/**
 * The brand field a signed-out screen opens with.
 *
 * [BrandHeader] gives the top of a *home* screen to the brand. This is its
 * counterpart for the screens reached before sign-in, where there is no
 * content to head and the problem is the opposite one: the sign-in form is
 * six controls on a 2400px display, so it sat in the top 45% with a thousand
 * pixels of dead white underneath. That emptiness is what made a carefully
 * built screen read as unfinished.
 *
 * So the brand takes the space instead of leaving it blank. The field runs
 * from behind the status bar down to a height the caller sets as a fraction of
 * the display, carries the name at display size, and the form sits on a card
 * that overlaps its lower edge -- which is what makes the card read as lying
 * *on* something rather than floating in a void.
 *
 * No photograph. The reference this borrows its shape from fills the same
 * zone with a vehicle render, which costs a megabyte of APK and a download on
 * a metered connection, in a market where both are scarce. A flat field and a
 * drawn texture cost nothing and survive a cheap panel in daylight.
 */
@Composable
fun BrandHero(
    title: String,
    subtitle: String,
    modifier: Modifier = Modifier,
    /**
     * A floor, not a fixed height.
     *
     * The caller passes a fraction of the display so the field scales with the
     * panel instead of being a number tuned on one handset. It is a minimum
     * because the text inside still has to fit: at the largest system font
     * size, in Pashto, the name and tagline are taller than the floor, and a
     * fixed height would clip them.
     */
    minHeight: Dp = 0.dp,
    content: @Composable ColumnScope.() -> Unit = {},
) {
    // The status bar sits on the green while this is on screen, so its icons
    // must be light -- and restored on the way out, because every other screen
    // keeps a white bar. Owned here for the same reason BrandHeader owns it:
    // the thing that causes the problem is the thing that undoes it.
    val view = LocalView.current
    if (!view.isInEditMode) {
        val window = (view.context as? Activity)?.window
        DisposableEffect(window) {
            val controller = window?.let { WindowCompat.getInsetsController(it, view) }
            val previous = controller?.isAppearanceLightStatusBars
            controller?.isAppearanceLightStatusBars = false
            onDispose {
                previous?.let { controller.isAppearanceLightStatusBars = it }
            }
        }
    }

    Surface(
        modifier = modifier.fillMaxWidth(),
        color = VelroColors.BrandField,
        contentColor = VelroColors.OnBrandField,
        shape = RoundedCornerShape(bottomStart = Radius.xl, bottomEnd = Radius.xl),
    ) {
        Box {
            // matchParentSize, not fillMaxSize: the Box is sized by the column
            // beside this, and fillMaxSize would resolve against the incoming
            // max constraint -- which is infinite, because a signed-out screen
            // scrolls so the keyboard has somewhere to push it. matchParentSize
            // measures after its siblings and takes the size they settled on.
            HaloTexture(Modifier.matchParentSize())

            Column(
                Modifier
                    // The floor belongs on the column, not the Surface. On the
                    // Surface it made the green tall while leaving the text a
                    // short box at the top of it, so Arrangement.Bottom had no
                    // room to work in and the field opened with 450px of empty
                    // green under the name.
                    .heightIn(min = minHeight)
                    .statusBarsPadding()
                    .padding(horizontal = Spacing.gutter)
                    .padding(top = Spacing.xxl, bottom = Spacing.xxxl),
                // The name sits on the floor of the field rather than the top,
                // so the gap between it and the card below stays constant
                // while the field itself grows with the display.
                verticalArrangement = Arrangement.Bottom,
            ) {
                Text(
                    title,
                    style = MaterialTheme.typography.displayLarge,
                    fontWeight = FontWeight.Bold,
                )
                Spacer(Modifier.height(Spacing.xs))
                Text(
                    subtitle,
                    style = MaterialTheme.typography.titleMedium,
                    // Deliberately not full white: a subtitle at the same
                    // weight as the name competes with it, and the pair should
                    // read as one block with an order to it.
                    color = VelroColors.Green100,
                )
                content()
            }
        }
    }
}

/**
 * The dot field in the corner of the brand surface.
 *
 * Drawn rather than shipped. A halftone that fades toward the centre gives the
 * flat green somewhere to catch the eye without adding an image, a gradient,
 * or a second colour -- the tokens allow exactly one accent per screen, and on
 * this screen the accent is spent on the button.
 *
 * Anchored to the *trailing* top corner, which is the left in Dari and Pashto
 * and the right in English. A Canvas draws in physical pixels and is not
 * mirrored for us the way a layout is, so the direction is read and the x
 * coordinate flipped by hand -- otherwise the texture stays welded to one
 * physical corner while every other element on the screen swaps sides.
 */
@Composable
private fun HaloTexture(modifier: Modifier = Modifier) {
    val rtl = LocalLayoutDirection.current == LayoutDirection.Rtl
    Canvas(modifier) {
        val step = 14.dp.toPx()
        val radius = 1.6.dp.toPx()
        val columns = 7
        val rows = 7
        for (c in 0 until columns) {
            for (r in 0 until rows) {
                // Fades out with distance from the corner, so the texture has
                // a source rather than being an even screen of dots.
                val falloff = 1f - ((c + r) / (columns + rows).toFloat())
                val inset = (c + 1) * step
                drawCircle(
                    color = VelroColors.Green200,
                    radius = radius,
                    alpha = 0.30f * falloff,
                    center = androidx.compose.ui.geometry.Offset(
                        x = if (rtl) inset else size.width - inset,
                        y = (r + 1) * step,
                    ),
                )
            }
        }
    }
}
