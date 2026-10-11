package af.velro.core.ui.component

import af.velro.core.ui.theme.Elevation
import af.velro.core.ui.theme.Glass
import af.velro.core.ui.theme.LocalVelroDarkTheme
import af.velro.core.ui.theme.Radius
import af.velro.core.ui.theme.Sizing
import af.velro.core.ui.theme.Spacing
import android.os.Build
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/**
 * The surfaces of the soft redesign: a shadow you would not name if asked,
 * and frosted glass for whatever floats over a map.
 */

/**
 * A wide, faint shadow in place of a hard edge.
 *
 * Android multiplies a shadow colour's alpha by the theme's own shadow alpha
 * (about a fifth for the spot shadow), so the strengths here are what is
 * handed to the platform, not what lands on the glass: [SHADOW_CARD] comes out
 * at roughly six percent black, which is the "soft and almost minimal" the
 * owner asked for.
 *
 * Android 8 and older ignore a shadow's colour and draw every one at full
 * strength, so there the elevation is quartered instead -- otherwise the
 * cheapest handsets, which are most of them here, would get the heavy grey
 * drop shadow the redesign exists to remove.
 */
fun Modifier.softShadow(
    shape: Shape,
    elevation: Dp = Elevation.card,
    color: Color = Color.Black,
    strength: Float = SHADOW_CARD,
): Modifier =
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
        shadow(
            elevation = elevation,
            shape = shape,
            clip = false,
            ambientColor = color.copy(alpha = strength * AMBIENT_SHARE),
            spotColor = color.copy(alpha = strength),
        )
    } else {
        shadow(elevation = elevation / 4, shape = shape, clip = false)
    }

/**
 * The shadow under a piece of glass, drawn by hand and only outside it.
 *
 * The platform's shadow is cast under the whole shape and assumes the shape
 * is opaque: under translucent glass it shows through, as a grey rim with a
 * hard-edged lighter rectangle inside it where the renderer skips the middle.
 * This draws a few widening rounded rings round the outside instead -- a
 * blur, approximated, that never enters the glass -- nudged down a little so
 * it reads as light from above. A handful of strokes, on every API level the
 * app supports, with nothing to show through.
 *
 * @param corner the shape's corner radius; null for a pill or a circle, whose
 *   radius is half its height.
 */
fun Modifier.glassShadow(
    corner: Dp? = null,
    spread: Dp = GLASS_SPREAD,
    strength: Float = GLASS_SHADOW,
): Modifier = drawBehind {
    val reach = spread.toPx()
    val rings = GLASS_RINGS
    val step = reach / rings
    val drop = reach * 0.25f
    val base = corner?.toPx() ?: (size.height / 2f)
    for (i in 1..rings) {
        val d = step * (i - 0.5f)
        // Falls away with the square of the distance, the way a soft
        // shadow's edge does.
        val fade = (1f - (i - 1f) / rings).let { it * it }
        drawRoundRect(
            color = Color.Black.copy(alpha = strength * fade),
            topLeft = Offset(-d, -d + drop),
            size = Size(size.width + d * 2, size.height + d * 2),
            cornerRadius = CornerRadius(base + d),
            style = Stroke(width = step * 1.05f),
        )
    }
}

/** How far a glass shadow reaches past the edge. */
private val GLASS_SPREAD = 14.dp

/** The darkest ring, at the edge: faint, by the owner's "almost minimal". */
private const val GLASS_SHADOW = 0.035f

private const val GLASS_RINGS = 7

/** About six percent once the platform has applied its own alpha. */
const val SHADOW_CARD = 0.32f

/** The primary button's green glow: present, never a smudge. */
const val SHADOW_BUTTON = 0.55f

/** The ambient half is wider and fainter than the spot half. */
private const val AMBIENT_SHARE = 0.5f

/**
 * The fill and rim of a piece of frosted glass, in the theme in force.
 *
 * One place, so the round buttons, the pill, the bar, the drawer and the
 * sheet are all the same glass rather than five near-matches.
 */
@Composable
fun glassFill(opacity: Float = Glass.FLOATING): Color =
    MaterialTheme.colorScheme.surface.copy(alpha = opacity)

@Composable
fun glassRim(): BorderStroke = BorderStroke(
    1.dp,
    Color.White.copy(
        alpha = if (LocalVelroDarkTheme.current) Glass.RIM_DARK else Glass.RIM_LIGHT,
    ),
)

/**
 * A round control over the map: the menu, the account.
 *
 * The glass circle is the whole touch target -- 52dp, not a 40dp circle with
 * invisible padding round it -- because over a map the edge you can see is
 * the edge people aim for, and a gloved thumb in a Ghorband winter needs all
 * of it.
 */
@Composable
fun GlassIconButton(
    icon: ImageVector,
    contentDescription: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    tint: Color = MaterialTheme.colorScheme.onSurface,
) {
    Surface(
        onClick = onClick,
        shape = CircleShape,
        color = glassFill(),
        contentColor = tint,
        border = glassRim(),
        modifier = modifier
            .glassShadow()
            .size(Sizing.touchTarget),
    ) {
        Box(contentAlignment = Alignment.Center) {
            Icon(icon, contentDescription = contentDescription, modifier = Modifier.size(Sizing.iconMd))
        }
    }
}

/**
 * A labelled control over the map: the help door on home.
 *
 * A label as well as an icon, because this one must be found by somebody who
 * has never opened the app before and is frightened -- a shield alone is a
 * guess, "Get help" is not.
 */
@Composable
fun GlassPillButton(
    label: String,
    icon: ImageVector?,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    iconTint: Color = MaterialTheme.colorScheme.primary,
) {
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(Radius.pill),
        color = glassFill(),
        contentColor = MaterialTheme.colorScheme.onSurface,
        border = glassRim(),
        modifier = modifier
            .glassShadow()
            .heightIn(min = Sizing.touchTarget),
    ) {
        Row(
            Modifier.padding(horizontal = Spacing.lg),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.Center,
        ) {
            if (icon != null) {
                Icon(icon, contentDescription = null, tint = iconTint, modifier = Modifier.size(Sizing.iconSm + 2.dp))
                Spacer(Modifier.width(Spacing.sm))
            }
            Text(label, style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.Bold)
        }
    }
}

/**
 * The grab bar at the top of a sheet.
 *
 * Decorative: the sheets here scroll rather than drag, and a screen reader
 * announcing a handle it cannot use would be a promise the screen does not
 * keep.
 */
@Composable
fun SheetHandle(modifier: Modifier = Modifier) {
    Box(
        modifier
            .fillMaxWidth()
            .padding(top = Spacing.sm, bottom = Spacing.xs),
        contentAlignment = Alignment.Center,
    ) {
        Box(
            Modifier
                .size(width = 40.dp, height = 4.dp)
                .background(MaterialTheme.colorScheme.outlineVariant, RoundedCornerShape(Radius.pill)),
        )
    }
}

/** Tall enough for a title and a subtitle in Perso-Arabic leading. */
internal val ROW_MIN_HEIGHT = 64.dp
