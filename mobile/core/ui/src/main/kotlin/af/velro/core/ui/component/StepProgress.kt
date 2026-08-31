package af.velro.core.ui.component

import af.velro.core.ui.theme.LocalAnimationsEnabled
import af.velro.core.ui.theme.Motion
import af.velro.core.ui.theme.Radius
import af.velro.core.ui.theme.Spacing
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.snap
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp

/**
 * Where you are in a multi-step form.
 *
 * The booking flow is seven steps and said so nowhere. A passenger who had
 * chosen a district, a village and a station had no way to know whether two
 * more were coming or five, which is the difference between finishing a form
 * and abandoning one -- and on a metered connection, abandoning it after
 * paying for the data that loaded it.
 *
 * Segments rather than one continuous bar, because the count is the thing
 * being communicated. A bar at 43% says "some of the way"; four segments lit
 * of seven says "three left", which is what somebody deciding whether to
 * carry on actually wants.
 *
 * Mirrors for free: this is a Row, so the first segment sits at the start,
 * which is the right in Dari and Pashto.
 */
@Composable
fun StepProgress(
    current: Int,
    total: Int,
    modifier: Modifier = Modifier,
    /** For the screen reader: "step 3 of 7", already localised by the caller. */
    label: String? = null,
) {
    val animate = LocalAnimationsEnabled.current
    val spec =
        if (animate) tween<androidx.compose.ui.graphics.Color>(Motion.WITHIN_MS, easing = Motion.easing)
        else snap()

    Row(
        modifier
            .fillMaxWidth()
            .padding(vertical = Spacing.sm)
            .then(
                if (label != null) Modifier.semantics { contentDescription = label }
                else Modifier,
            ),
        horizontalArrangement = Arrangement.spacedBy(Spacing.xs),
    ) {
        for (index in 0 until total) {
            // The colour animates, not the width. A segment growing into place
            // would move every segment after it, and a row that reflows on
            // every step is the kind of motion that draws the eye away from
            // the thing that actually changed -- the list underneath.
            val reached = index <= current
            val colour by animateColorAsState(
                targetValue =
                    if (reached) MaterialTheme.colorScheme.primary
                    else MaterialTheme.colorScheme.outlineVariant,
                animationSpec = spec,
                label = "step-$index",
            )
            Segment(colour)
        }
    }
}

@Composable
private fun RowScope.Segment(colour: androidx.compose.ui.graphics.Color) {
    androidx.compose.foundation.layout.Box(
        Modifier
            .weight(1f)
            .height(4.dp)
            .background(colour, RoundedCornerShape(Radius.pill)),
    )
}
