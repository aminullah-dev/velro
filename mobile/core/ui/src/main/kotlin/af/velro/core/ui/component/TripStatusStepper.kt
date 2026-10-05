package af.velro.core.ui.component

import af.velro.core.ui.theme.LocalAnimationsEnabled
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.domain.BookingStatus
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.DirectionsCar
import androidx.compose.material.icons.filled.EventSeat
import androidx.compose.material.icons.filled.Flag
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp

/**
 * The ride's life as a row of stops: what is done is filled and ticked, where
 * it is now is lit with a breathing ring, what is ahead is a hollow outline.
 *
 * Icons rather than words -- the clearest "a ride is being watched" signal a
 * transport app carries, read at a glance by a passenger who cannot read the
 * station names. The Row follows the layout direction, so in Dari and Pashto
 * the first stop sits on the right and the ride runs leftward.
 *
 * A failed ride shows nothing: the status pill beside it already says
 * cancelled, and a half-lit track would only argue with it.
 */
@Composable
fun TripStatusStepper(status: BookingStatus, modifier: Modifier = Modifier) {
    val current = when (status) {
        // Pending and confirmed are one stop to a passenger: the car is asked
        // for, no one is assigned yet.
        BookingStatus.PENDING, BookingStatus.CONFIRMED -> 0
        BookingStatus.DRIVER_ASSIGNED -> 1
        BookingStatus.READY -> 2
        BookingStatus.ONBOARD -> 3
        BookingStatus.COMPLETED -> 4
        BookingStatus.CANCELLED, BookingStatus.NO_SHOW -> -1
    }
    if (current < 0) return

    val strings = LocalVelroStrings.current
    val icons = listOf(
        Icons.AutoMirrored.Filled.Send,
        Icons.Filled.Person,
        Icons.Filled.DirectionsCar,
        Icons.Filled.EventSeat,
        Icons.Filled.Flag,
    )
    val labelKeys = listOf("confirmed", "driver_assigned", "ready", "onboard", "completed")

    Row(
        modifier
            .fillMaxWidth()
            .semantics { contentDescription = strings["booking.status." + labelKeys[current]] },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        icons.forEachIndexed { index, icon ->
            Node(index = index, current = current, icon = icon)
            if (index < icons.lastIndex) {
                Box(
                    Modifier
                        .weight(1f)
                        .height(3.dp)
                        .background(
                            if (index < current) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.outlineVariant
                        )
                )
            }
        }
    }
}

@Composable
private fun Node(index: Int, current: Int, icon: ImageVector) {
    val done = index < current
    val active = index == current
    val filled = done || active
    val primary = MaterialTheme.colorScheme.primary

    Box(contentAlignment = Alignment.Center, modifier = Modifier.size(44.dp)) {
        if (active) {
            // The breath around the live stop, present without motion too so it
            // is always findable, and only pulsing when the system allows it.
            if (LocalAnimationsEnabled.current) {
                val transition = rememberInfiniteTransition(label = "trip-stepper-pulse")
                val scale by transition.animateFloat(
                    initialValue = 0.85f, targetValue = 1.4f,
                    animationSpec = infiniteRepeatable(tween(1300), RepeatMode.Restart),
                    label = "scale",
                )
                val fade by transition.animateFloat(
                    initialValue = 0.9f, targetValue = 0f,
                    animationSpec = infiniteRepeatable(tween(1300), RepeatMode.Restart),
                    label = "fade",
                )
                Box(
                    Modifier
                        .size(28.dp)
                        .scale(scale)
                        .alpha(fade)
                        .clip(CircleShape)
                        .background(primary.copy(alpha = 0.22f))
                )
            }
            Box(Modifier.size(40.dp).clip(CircleShape).border(2.dp, primary.copy(alpha = 0.3f), CircleShape))
        }
        Box(
            contentAlignment = Alignment.Center,
            modifier = Modifier
                .size(if (active) 32.dp else 26.dp)
                .clip(CircleShape)
                .background(if (filled) primary else MaterialTheme.colorScheme.surfaceVariant)
                .then(
                    if (filled) Modifier
                    else Modifier.border(1.dp, MaterialTheme.colorScheme.outline, CircleShape)
                ),
        ) {
            Icon(
                imageVector = if (done) Icons.Filled.Check else icon,
                contentDescription = null,
                tint = if (filled) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.size(if (active) 17.dp else 14.dp),
            )
        }
    }
}
