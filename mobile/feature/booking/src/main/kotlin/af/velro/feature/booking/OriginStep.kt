package af.velro.feature.booking

import af.velro.core.ui.component.ChoiceChip
import af.velro.core.ui.component.IconRow
import af.velro.core.ui.component.PillField
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import af.velro.core.i18n.Strings
import af.velro.data.location.RecentOrigins
import af.velro.domain.Place
import af.velro.domain.Station
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.List
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.MyLocation
import androidx.compose.material.icons.filled.Place
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp

/**
 * Where from, opening on where the passenger is standing (ADR 0015).
 *
 * Laid out the way every ride app a passenger may have seen is: the current
 * location first, as one card that already knows the answer -- the district,
 * the station to walk to -- then the places around, then where she asked from
 * last time, and the full list last. A person at a roadside should reach
 * "where are you going" with one tap, and only type if she wants to.
 *
 * The name field is optional, and says why it is there: the driver reads it,
 * and so may the next passenger. Its refusals speak in reasons, never "invalid".
 */
@Composable
internal fun OriginStep(
    state: BookingFlowUiState,
    onEvent: (BookingEvent) -> Unit,
    locationAccess: LocationAccess,
    onRequestLocation: () -> Unit,
    onOpenLocationSettings: () -> Unit,
) {
    val strings = LocalVelroStrings.current
    LazyColumn(
        modifier = Modifier.imePadding(),
        verticalArrangement = Arrangement.spacedBy(Spacing.sm),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(top = Spacing.xs),
    ) {
        item(key = "here") {
            HereCard(state, onEvent, locationAccess, onRequestLocation, onOpenLocationSettings)
        }

        val places = state.whereabouts?.places.orEmpty()
            .filter { it.id != state.originPlace?.id }
        if (places.isNotEmpty()) {
            item(key = "places-title") { SectionTitle(strings["origin.section.nearby"]) }
            items(places, key = { "place-" + it.id }) { place ->
                OriginRow(
                    icon = Icons.Filled.Place,
                    title = place.name,
                    subtitle = place.distanceMetres?.let { distanceLabel(strings, it) },
                    onClick = { onEvent(BookingEvent.NearbyPlaceChosen(place)) },
                    modifier = Modifier.testTag("origin.place"),
                )
            }
        }

        if (state.recents.isNotEmpty()) {
            item(key = "recent-title") { SectionTitle(strings["origin.section.recent"]) }
            items(state.recents, key = { "recent-" + it.stationId + "-" + it.placeId }) { entry ->
                OriginRow(
                    icon = Icons.Filled.History,
                    title = entry.placeName?.let { strings["origin.place.saved", "place" to it] }
                        ?: entry.stationName,
                    subtitle = if (entry.placeName != null) entry.stationName else null,
                    onClick = { onEvent(BookingEvent.RecentChosen(entry)) },
                    modifier = Modifier.testTag("origin.recent"),
                )
            }
        }

        item(key = "browse") {
            Spacer(Modifier.height(Spacing.xs))
            OriginRow(
                icon = Icons.AutoMirrored.Filled.List,
                title = strings["origin.action.browse"],
                subtitle = null,
                onClick = { onEvent(BookingEvent.Browse) },
                modifier = Modifier.testTag("origin.browse"),
            )
            Spacer(Modifier.height(Spacing.xl))
        }
    }
}

@Composable
private fun HereCard(
    state: BookingFlowUiState,
    onEvent: (BookingEvent) -> Unit,
    locationAccess: LocationAccess,
    onRequestLocation: () -> Unit,
    onOpenLocationSettings: () -> Unit,
) {
    val strings = LocalVelroStrings.current
    VelroCard(modifier = Modifier.testTag("origin.here")) {
        Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Filled.MyLocation,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                )
                Spacer(Modifier.size(Spacing.sm))
                Text(
                    strings["origin.current.title"],
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f),
                )
                if (state.hereStatus == HereStatus.LOCATING) {
                    CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                }
            }

            when {
                locationAccess != LocationAccess.GRANTED -> NoAccess(
                    locationAccess, onRequestLocation, onOpenLocationSettings,
                )
                state.hereStatus == HereStatus.IDLE || state.hereStatus == HereStatus.LOCATING ->
                    Muted(strings["origin.current.locating"])
                state.hereStatus == HereStatus.UNAVAILABLE -> {
                    Muted(strings["origin.current.unavailable"])
                    SecondaryAction(
                        label = strings["origin.action.retry_location"],
                        onClick = onRequestLocation,
                    )
                }
                state.whereabouts?.inside != true -> Muted(strings["origin.current.outside"])
                else -> Found(state, onEvent, onRequestLocation)
            }
        }
    }
}

@Composable
private fun NoAccess(
    access: LocationAccess,
    onRequestLocation: () -> Unit,
    onOpenLocationSettings: () -> Unit,
) {
    val strings = LocalVelroStrings.current
    if (access == LocationAccess.DENIED) {
        Muted(strings["location.permission.denied"])
        SecondaryAction(
            label = strings["location.action.open_settings"],
            onClick = onOpenLocationSettings,
        )
    } else {
        // Why, before Android asks. The system dialog explains nothing.
        Muted(strings["location.permission.rationale"])
        PrimaryAction(
            label = strings["home.search.from_here"],
            onClick = onRequestLocation,
            modifier = Modifier.fillMaxWidth().testTag("origin.allow"),
        )
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Found(
    state: BookingFlowUiState,
    onEvent: (BookingEvent) -> Unit,
    onRequestLocation: () -> Unit,
) {
    val strings = LocalVelroStrings.current
    val here = state.whereabouts ?: return
    val stations = here.stations
    // Which station she will board at: the nearest, unless she picked another.
    var chosenId by rememberSaveable(stations.firstOrNull()?.id) {
        mutableStateOf(stations.firstOrNull()?.id)
    }
    val boarding: Station? = stations.firstOrNull { it.id == chosenId } ?: stations.firstOrNull()

    here.district?.let { district ->
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(
                if (here.districtIsGuess) {
                    strings["origin.current.district_guess", "district" to district.name]
                } else {
                    strings["origin.current.district", "district" to district.name]
                },
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.weight(1f),
            )
            // Change is the list: a guessed district is corrected by choosing
            // the village, which is the thing that was guessed at.
            TextButton(onClick = { onEvent(BookingEvent.Browse) }) {
                Text(strings["origin.action.change_district"])
            }
        }
    }

    boarding?.let { station ->
        Text(
            // No distance when she is standing at it: "0 m away" reads as a fault.
            strings["origin.current.nearest", "station" to station.name] +
                (station.distanceMetres?.takeIf { it >= 50 }
                    ?.let { " · " + distanceLabel(strings, it) } ?: ""),
            style = MaterialTheme.typography.bodyLarge,
            fontWeight = FontWeight.Medium,
        )
    }

    if (stations.size > 1) {
        Muted(strings["origin.current.other_station"])
        // Wraps: three Dari station names do not fit one row, and a cut-off
        // "ایستگاه" is a chip nobody can choose with confidence.
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
            verticalArrangement = Arrangement.spacedBy(Spacing.xs),
        ) {
            stations.take(3).forEach { station ->
                ChoiceChip(
                    selected = station.id == boarding?.id,
                    onClick = { chosenId = station.id },
                    label = station.name,
                )
            }
        }
    }

    HorizontalDivider(Modifier.padding(vertical = Spacing.xs))
    PlaceName(state, onEvent, onRequestLocation)

    PrimaryAction(
        label = strings["origin.current.use"],
        onClick = { boarding?.let { onEvent(BookingEvent.TravelFromHere(it)) } },
        enabled = boarding != null && !state.isNamingPlace,
        loading = state.isNamingPlace,
        modifier = Modifier.fillMaxWidth().testTag("origin.use"),
    )
}

/**
 * "What is this place called?" -- optional, and never the thing that stops a
 * passenger from travelling: leaving it empty is the same as skipping it.
 */
@Composable
private fun PlaceName(
    state: BookingFlowUiState,
    onEvent: (BookingEvent) -> Unit,
    onRequestLocation: () -> Unit,
) {
    val strings = LocalVelroStrings.current
    val saved = state.originPlace

    if (saved != null && saved.name == state.placeName.trim()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(
                Icons.Filled.CheckCircle,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
                modifier = Modifier.size(20.dp),
            )
            Spacer(Modifier.size(Spacing.sm))
            Text(
                strings["origin.place.saved", "place" to saved.name],
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.weight(1f),
            )
            TextButton(onClick = { onEvent(BookingEvent.ClearPlace) }) {
                Text(strings["origin.place.change"])
            }
        }
        if (saved.pending) Muted(strings["origin.place.pending"])
        return
    }

    if (!state.canNamePlace) {
        // A coarse fix: offering the field would only collect a refusal.
        Muted(strings["origin.place.need_precise"])
        TextButton(onClick = onRequestLocation) {
            Text(strings["origin.action.retry_location"])
        }
        return
    }

    PillField(
        value = state.placeName,
        onValueChange = { onEvent(BookingEvent.PlaceNameChanged(it)) },
        label = strings["origin.place.question"],
        placeholder = strings["origin.place.hint"],
        isError = state.placeRefusal != null,
        supportingText = state.placeRefusal?.let { reason -> refusalText(strings, reason) },
        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
        keyboardActions = KeyboardActions(onDone = { onEvent(BookingEvent.SavePlaceName) }),
        fieldModifier = Modifier.testTag("origin.place_name"),
    )
    // The first letters of a spot the valley already knows bring its whole
    // name back -- tap it and the station and coordinates behind it come with
    // it, rather than naming the place a second time.
    state.placeSuggestions.forEach { place ->
        OriginRow(
            icon = Icons.Filled.Place,
            title = place.name,
            subtitle = place.distanceMetres?.let { distanceLabel(strings, it) },
            onClick = { onEvent(BookingEvent.SuggestionChosen(place)) },
            modifier = Modifier.testTag("origin.suggestion"),
        )
    }
    if (state.placeRefusal == null) Muted(strings["origin.place.why"])
    if (state.placeName.isNotBlank()) {
        SecondaryAction(
            label = strings["origin.place.save"],
            onClick = { onEvent(BookingEvent.SavePlaceName) },
            modifier = Modifier.testTag("origin.place_save"),
        )
    }
}

/**
 * The server's reason, in words. A literal key per reason: the localisation
 * guard reads source for the keys the apps ask for, and a key built at runtime
 * would be invisible to it.
 */
private fun refusalText(strings: Strings, reason: String): String = when {
    reason == "personal" -> strings["origin.place.refused.personal"]
    reason == "digits" || reason == "contact" -> strings["origin.place.refused.digits"]
    reason == "generic" -> strings["origin.place.refused.generic"]
    reason == "too_long" || reason == "empty" -> strings["origin.place.refused.too_long"]
    reason == "rejected" -> strings["origin.place.refused.rejected"]
    reason == "coarse" -> strings["origin.place.need_precise"]
    reason.startsWith("error:") -> strings.forErrorCode(reason.removePrefix("error:"), emptyMap())
    else -> strings["origin.place.refused.personal"]
}

private fun distanceLabel(strings: Strings, metres: Int): String =
    if (metres >= 1000) strings["location.distance.kilometres", "distance" to metres / 1000]
    else strings["location.distance.metres", "distance" to metres]

@Composable
private fun SectionTitle(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.titleSmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(top = Spacing.md, bottom = Spacing.xs),
    )
}

@Composable
private fun Muted(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@Composable
private fun OriginRow(
    icon: ImageVector,
    title: String,
    subtitle: String?,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    // The soft list row every list in the flow now uses.
    IconRow(
        title = title,
        subtitle = subtitle,
        icon = icon,
        onClick = onClick,
        modifier = modifier,
    )
}
