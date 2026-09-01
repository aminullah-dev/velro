package af.velro.feature.trip

import af.velro.core.i18n.Numerals
import af.velro.core.map.JourneyMap
import af.velro.core.ui.component.PhotoAvatar
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Sizing
import af.velro.core.ui.theme.Spacing
import af.velro.data.repository.RideDriver
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Call
import androidx.compose.material3.Button
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

/**
 * The ride, watched.
 *
 * Map first and most: the reference this answers to gives the journey the
 * top half of the screen, and so does this -- the small card on the booking
 * page opens into it. Below the map, only what a person standing at a
 * roadside actually needs: how long until the car, whose car, which plate
 * to check against the one that stops, and a button that dials -- because
 * in this product's world a phone call is the chat system, and it has
 * never needed installing.
 *
 * Every number defends itself. The minutes come from the road's own length
 * and the routing engine's own average for it, or they are absent; the
 * dot's age is printed under it; a booking with no driver yet says so
 * instead of pretending.
 */
@Composable
fun TrackRideRoute(
    onBack: () -> Unit,
    viewModel: TrackRideViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val strings = LocalVelroStrings.current
    val context = LocalContext.current

    Scaffold(
        topBar = {
            Row(
                Modifier
                    .fillMaxWidth()
                    .padding(horizontal = Spacing.sm, vertical = Spacing.xs),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(onClick = onBack) {
                    Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = null)
                }
                Text(
                    strings["track.title"],
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.SemiBold,
                )
            }
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding)) {
            state.journeyMap?.let { drawn ->
                JourneyMap(
                    drawn,
                    vehicle = state.vehicle,
                    modifier = Modifier.weight(1f),
                )
            } ?: Spacer(Modifier.weight(1f))

            Column(
                Modifier
                    .fillMaxWidth()
                    .padding(Spacing.md),
                verticalArrangement = Arrangement.spacedBy(Spacing.sm),
            ) {
                Eta(state)
                state.driver?.let { DriverCard(it, state.driverPhoto) { number ->
                    // DIAL, not CALL: the dialer opens with the number and the
                    // passenger presses the green button herself. No
                    // permission, no surprise call from a pocket.
                    runCatching {
                        context.startActivity(
                            Intent(Intent.ACTION_DIAL, Uri.parse("tel:$number"))
                        )
                    }
                } } ?: Text(
                    strings["track.awaiting_driver"],
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                JourneyEnds(state)
            }
        }
    }
}

@Composable
private fun Eta(state: TrackRideUiState) {
    val strings = LocalVelroStrings.current
    val minutes = state.etaMinutes
    Column {
        Text(
            when {
                minutes == null -> strings["track.eta_unknown"]
                minutes < 3 -> strings["track.eta_now"]
                else -> strings[
                    "track.eta",
                    "minutes" to Numerals.localise(minutes.toString(), strings.locale),
                ]
            },
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
        )
        state.vehicleAgeSeconds?.let { age ->
            Text(
                if (age < 90) strings["trip.vehicle_seen_now"]
                else strings[
                    "trip.vehicle_seen",
                    "minutes" to Numerals.localise((age / 60).toString(), strings.locale),
                ],
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun DriverCard(driver: RideDriver, photo: ByteArray?, onCall: (String) -> Unit) {
    val strings = LocalVelroStrings.current
    VelroCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            PhotoAvatar(bytes = photo, size = Sizing.avatar)
            Spacer(Modifier.height(Spacing.xs))
            Column(Modifier.weight(1f)) {
                Text(
                    driver.name ?: strings["common.value.no_name"],
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                driver.ratingAverage?.let { rating ->
                    Text(
                        "★ " + Numerals.localise(
                            String.format(java.util.Locale.US, "%.1f", rating),
                            strings.locale,
                        ),
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                driver.vehicle?.let { vehicle ->
                    Text(
                        listOfNotNull(vehicle.brand, vehicle.model, vehicle.colour)
                            .joinToString(" ") + " — " + vehicle.plateNumber,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
            Button(onClick = { onCall(driver.phone) }) {
                Icon(Icons.Filled.Call, contentDescription = null)
                Text(strings["track.call"])
            }
        }
    }
}

@Composable
private fun JourneyEnds(state: TrackRideUiState) {
    val strings = LocalVelroStrings.current
    val map = state.journeyMap ?: return
    VelroCard {
        Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
            map.origin?.let {
                Text(
                    strings["location.label.origin"] + ": " + it.name,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
            map.destination?.let {
                Text(
                    strings["location.label.destination"] + ": " + it.name,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }
}
