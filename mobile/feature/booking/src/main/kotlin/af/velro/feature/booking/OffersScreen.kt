package af.velro.feature.booking

import af.velro.core.i18n.MoneyFormatter
import af.velro.core.i18n.Numerals
import af.velro.core.ui.component.ErrorState
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import af.velro.domain.FareOffer
import af.velro.domain.MoneyValue
import af.velro.domain.RideRequest
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Star
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun OffersRoute(
    onRideAgreed: (String) -> Unit,
    onFinished: () -> Unit,
    viewModel: OffersViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    // The moment a price is agreed the journey exists, so the passenger is
    // taken to it rather than left on a list of prices that no longer matter.
    LaunchedEffect(state.accepted) {
        state.accepted?.let { onRideAgreed(it.bookingId) }
    }
    LaunchedEffect(state.cancelled) {
        if (state.cancelled) onFinished()
    }

    OffersScreen(state, viewModel::onEvent)
}

@Composable
fun OffersScreen(
    state: OffersUiState,
    onEvent: (OffersEvent) -> Unit,
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current
    val request = state.request

    if (state.isLoading && request == null) {
        LoadingState(modifier.fillMaxSize())
        return
    }
    if (request == null) {
        ErrorState(
            errorCode = state.errorCode ?: "RIDE_REQUEST_NOT_FOUND",
            context = state.errorContext,
            onRetry = { onEvent(OffersEvent.Refresh) },
            modifier = modifier.fillMaxSize(),
        )
        return
    }

    Column(
        modifier
            .fillMaxSize()
            .statusBarsPadding()
            .padding(horizontal = Spacing.gutter),
    ) {
        Spacer(Modifier.height(Spacing.md))
        Journey(request)
        Spacer(Modifier.height(Spacing.md))

        if (state.errorCode != null) {
            InlineError(state.errorCode!!, context = state.errorContext)
        }

        val offers = request.liveOffers
        if (offers.isEmpty()) {
            Spacer(Modifier.weight(1f))
            Waiting()
            Spacer(Modifier.weight(1f))
        } else {
            Text(
                strings["ride.offers.title"],
                style = MaterialTheme.typography.titleMedium,
            )
            Spacer(Modifier.height(Spacing.sm))
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                modifier = Modifier.weight(1f),
            ) {
                items(offers, key = { it.id }) { offer ->
                    OfferCard(
                        offer = offer,
                        asking = request.offeredFare,
                        accepting = state.acceptingOfferId == offer.id,
                        // One action in flight at a time: two taps on a slow
                        // connection must not agree two fares.
                        enabled = state.acceptingOfferId == null,
                        onAccept = { onEvent(OffersEvent.Accept(offer.id)) },
                    )
                }
            }
        }

        Spacer(Modifier.height(Spacing.sm))
        SecondaryAction(
            label = strings["ride.action.cancel"],
            onClick = { onEvent(OffersEvent.Cancel) },
            enabled = !state.isCancelling && state.acceptingOfferId == null,
            modifier = Modifier.fillMaxWidth(),
        )
        Spacer(Modifier.height(Spacing.lg))
    }
}

@Composable
private fun Journey(request: RideRequest) {
    val strings = LocalVelroStrings.current
    VelroCard {
        Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
            Text(
                strings[
                    "ride.journey.from_to",
                    "origin" to (request.originStationName ?: "—"),
                    "destination" to (request.destinationName ?: "—"),
                ],
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                strings[
                    "ride.offers.you_asked",
                    "amount" to MoneyFormatter.format(request.offeredFare, strings),
                ],
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun Waiting() {
    val strings = LocalVelroStrings.current
    Column(
        Modifier.fillMaxWidth().padding(vertical = Spacing.xl),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(Spacing.md),
    ) {
        // A spinner, because something really is coming: drivers are being
        // shown this request now. An empty state would say the opposite.
        CircularProgressIndicator()
        Text(
            strings["ride.offers.waiting"],
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun OfferCard(
    offer: FareOffer,
    asking: MoneyValue,
    accepting: Boolean,
    enabled: Boolean,
    onAccept: () -> Unit,
) {
    val strings = LocalVelroStrings.current
    val agrees = offer.agreesWith(asking)
    val difference = offer.differenceFrom(asking)

    VelroCard {
        Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(
                        offer.driverName ?: "—",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(Spacing.xs),
                    ) {
                        offer.driverRating?.let { rating ->
                            Icon(
                                Icons.Filled.Star,
                                // The rating is written beside it, so the star
                                // is decoration and is hidden from a reader.
                                contentDescription = null,
                                modifier = Modifier.height(14.dp),
                                tint = MaterialTheme.colorScheme.secondary,
                            )
                            Text(
                                Numerals.localise(rating.toString(), strings.locale),
                                style = MaterialTheme.typography.labelMedium,
                            )
                        }
                        Text(
                            strings["ride.offers.trips", "count" to offer.driverTrips],
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(
                        MoneyFormatter.format(offer.amount, strings),
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                    )
                    // How it compares with what was asked, so nobody has to
                    // subtract one number from another at a roadside.
                    Text(
                        if (agrees) strings["ride.offers.same_as_asked"]
                        else {
                            val sign = if (difference.amountMinor > 0) "+" else "−"
                            sign + MoneyFormatter.format(
                                MoneyValue(
                                    kotlin.math.abs(difference.amountMinor),
                                    difference.currency,
                                ),
                                strings,
                            )
                        },
                        style = MaterialTheme.typography.labelSmall,
                        color = if (agrees || difference.amountMinor < 0)
                            MaterialTheme.colorScheme.primary
                        else MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }

            offer.vehiclePlate?.let { plate ->
                Row(
                    horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    // Read off a physical car: never mirrored, never in
                    // Eastern digits.
                    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                        Text(plate, style = MaterialTheme.typography.bodyMedium,
                             fontWeight = FontWeight.Medium)
                    }
                    offer.vehicleDescription?.let {
                        Text(
                            it,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
            }

            offer.note?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            Spacer(Modifier.height(Spacing.xs))
            HorizontalDivider()
            Spacer(Modifier.height(Spacing.xs))

            PrimaryAction(
                label = strings["ride.offers.accept"],
                onClick = onAccept,
                enabled = enabled,
                loading = accepting,
                // Comfortably above the 48dp Android minimum: this is the one
                // tap on the screen that costs money.
                modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp),
            )
        }
    }
}
