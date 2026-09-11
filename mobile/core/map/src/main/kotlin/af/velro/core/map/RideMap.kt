package af.velro.core.map

import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Radius
import af.velro.core.ui.theme.Spacing
import af.velro.data.repository.MapPlace
import af.velro.data.repository.TripMapData
import af.velro.data.tracking.RoadAhead
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/**
 * The ride itself, on both phones in the car.
 *
 * Once the passenger is on board the working screens step aside: the map
 * takes the whole display, the road's next warning sits at the top, and the
 * foot says who is in the car -- the driver's name and the passengers' --
 * and nothing else. The owner asked for exactly this shape after the first
 * real trip, so the two phones show the same journey at the same moment.
 *
 * Two things are kept beyond what was asked, deliberately. Help stays, as a
 * small door at the top: this is the screen a passenger is looking at in the
 * car, which is the case ADR 0010 was written for. And the driver keeps his
 * one next step, passed in as [action], because a ride screen with no way to
 * say "arrived" is a ride that cannot end.
 */
@Composable
fun RideMap(
    data: TripMapData?,
    roadAhead: RoadAhead.Next?,
    driverName: String?,
    passengerNames: List<String>,
    onHelp: () -> Unit,
    modifier: Modifier = Modifier,
    /** The car, on the passenger's phone. The driver sees his own blue dot. */
    vehicle: MapPlace? = null,
    /** The driver's phone chimes as he enters a zone; hers stays quiet. */
    chime: Boolean = false,
    action: @Composable () -> Unit = {},
) {
    Box(modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
        data?.let { JourneyMap(it, vehicle = vehicle, modifier = Modifier.fillMaxSize(), fullBleed = true) }

        Column(
            Modifier
                .fillMaxSize()
                .statusBarsPadding()
                .navigationBarsPadding()
                .padding(horizontal = Spacing.lg, vertical = Spacing.sm),
        ) {
            Row(verticalAlignment = Alignment.Top) {
                Box(Modifier.weight(1f)) { RoadAheadBanner(roadAhead, chime) }
                Spacer(Modifier.width(Spacing.sm))
                HelpDoor(onHelp)
            }
            Spacer(Modifier.weight(1f))
            RideNames(driverName, passengerNames)
            action()
        }
    }
}

/**
 * The road's next warning: the warning itself once the car is in it, and how
 * far off it is before. Nothing when the road ahead is clear or the car's
 * position is unknown -- an empty banner reads as a warning about nothing.
 */
@Composable
fun RoadAheadBanner(next: RoadAhead.Next?, chime: Boolean = false) {
    val strings = LocalVelroStrings.current
    next ?: return

    // One chime as he enters a zone, from the notification stream so it
    // respects the ringer: eyes belong on the road, and the sound is what
    // makes him glance down once.
    if (chime) {
        LaunchedEffect(next.messageKey, next.inside) {
            if (!next.inside) return@LaunchedEffect
            runCatching {
                val tone = android.media.ToneGenerator(android.media.AudioManager.STREAM_NOTIFICATION, 85)
                try {
                    tone.startTone(android.media.ToneGenerator.TONE_PROP_BEEP2, 400)
                    kotlinx.coroutines.delay(500)
                } finally {
                    tone.release()
                }
            }
        }
    }

    Surface(
        color = if (next.inside) MaterialTheme.colorScheme.errorContainer else MaterialTheme.colorScheme.surface,
        contentColor = if (next.inside) MaterialTheme.colorScheme.onErrorContainer else MaterialTheme.colorScheme.onSurface,
        shape = RoundedCornerShape(Radius.lg),
        shadowElevation = 4.dp,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(Spacing.md), verticalArrangement = Arrangement.spacedBy(Spacing.xxs)) {
            Text(
                strings["notif.road.title"],
                style = MaterialTheme.typography.labelMedium,
                color = if (next.inside) MaterialTheme.colorScheme.onErrorContainer
                else MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(strings[next.messageKey], style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
            if (!next.inside) {
                Text(
                    if (next.metres >= 1000) {
                        strings["location.distance.kilometres", "distance" to next.metres / 1000]
                    } else {
                        strings["location.distance.metres", "distance" to next.metres]
                    },
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun HelpDoor(onHelp: () -> Unit) {
    val strings = LocalVelroStrings.current
    Surface(
        color = MaterialTheme.colorScheme.error,
        contentColor = MaterialTheme.colorScheme.onError,
        shape = RoundedCornerShape(Radius.pill),
        shadowElevation = 4.dp,
    ) {
        TextButton(onClick = onHelp, modifier = Modifier.heightIn(min = 52.dp)) {
            Text(strings["safety.title"], color = MaterialTheme.colorScheme.onError, fontWeight = FontWeight.Bold)
        }
    }
}

/** Who is in the car, and nothing else. */
@Composable
private fun RideNames(driverName: String?, passengerNames: List<String>) {
    val strings = LocalVelroStrings.current
    val noName = strings["common.value.no_name"]
    Surface(
        color = MaterialTheme.colorScheme.surface,
        shape = RoundedCornerShape(Radius.card),
        shadowElevation = 6.dp,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(Spacing.lg)) {
            NameRow(strings["trip.label.driver"], driverName?.takeIf { it.isNotBlank() } ?: noName)
            HorizontalDivider(Modifier.padding(vertical = Spacing.sm))
            NameRow(
                strings["driver.label.passengers"],
                passengerNames.filter { it.isNotBlank() }.ifEmpty { listOf(noName) }.joinToString("، "),
            )
        }
    }
}

@Composable
private fun NameRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(
            label,
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(1f),
        )
        Text(value, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
    }
}
