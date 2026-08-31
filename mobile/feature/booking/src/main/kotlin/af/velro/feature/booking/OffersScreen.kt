package af.velro.feature.booking

import af.velro.core.i18n.MoneyFormatter
import af.velro.core.i18n.Numerals
import af.velro.core.ui.component.ErrorState
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.PrimaryAction
import af.velro.domain.RideRequestStatus
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.component.VelroScreen
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Sizing
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
import androidx.compose.foundation.layout.size
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
import androidx.compose.ui.text.style.TextAlign
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

    OffersScreen(state, viewModel::onEvent, onAskAgain = onFinished)
}

@Composable
fun OffersScreen(
    state: OffersUiState,
    onEvent: (OffersEvent) -> Unit,
    /** Back to where a ride is asked for. The way out of a closed request. */
    onAskAgain: () -> Unit = {},
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

    VelroScreen(
        title = strings["ride.offers.title"],
        // Back leaves the request open on the server rather than
        // cancelling it: a passenger who glances at the home screen has
        // not withdrawn their ask, and drivers are still bidding on it.
        onBack = onAskAgain,
        scrollable = false,
        modifier = modifier,
    ) {
        Spacer(Modifier.height(Spacing.md))
        Journey(request)
        Spacer(Modifier.height(Spacing.md))

        if (state.errorCode != null) {
            InlineError(state.errorCode!!, context = state.errorContext)
        }

        val offers = request.liveOffers
        // The status decides, not the emptiness of the list. The server closes
        // a stale request on this very read, so once the TTL passes the reply
        // is EXPIRED with no live offers -- and a screen branching on the list
        // alone draws a spinner over "waiting for drivers" forever, while the
        // view model stops polling because the request is no longer open. The
        // passenger is left watching an animation for something that already
        // finished without them.
        if (!request.isOpen) {
            Spacer(Modifier.weight(1f))
            RequestClosed(
                status = request.status,
                onAskAgain = onAskAgain,
            )
            Spacer(Modifier.weight(1f))
        } else if (offers.isEmpty()) {
            Spacer(Modifier.weight(1f))
            Waiting()
            Spacer(Modifier.weight(1f))
        } else {
            // No heading here: the app bar already says "drivers who answered",
            // and the screen's decisive moment should open with the answers
            // rather than with its own title said twice.
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                modifier = Modifier.weight(1f),
            ) {
                items(offers, key = { it.id }) { offer ->
                    OfferCard(
                        // This list changes under the passenger's finger.
                        //
                        // Drivers bid while the screen is open, so a reply can
                        // arrive in the moment somebody is reaching for
                        // "accept" -- and without animation the row they aimed
                        // at is simply somewhere else by the time the tap
                        // lands. That is not a polish problem: it is agreeing
                        // a fare with the wrong driver.
                        //
                        // The insert is animated so the shift is something the
                        // eye can follow, and `key` above is what lets Compose
                        // tell an inserted offer from a moved one.
                        modifier = Modifier.animateItem(),
                        offer = offer,
                        // The whole journey, not the outbound leg: on a
                        // round trip `offeredFare` is half the ask, and
                        // every reply would look expensive against it.
                        asking = request.askingTotal,
                        accepting = state.acceptingOfferId == offer.id,
                        // One action in flight at a time: two taps on a slow
                        // connection must not agree two fares.
                        enabled = state.acceptingOfferId == null,
                        onAccept = { onEvent(OffersEvent.Accept(offer.id)) },
                    )
                }
            }
        }

        // Only while there is something to cancel.
        //
        // This rendered after every branch, so a passenger whose ask had
        // expired -- the common ending -- was shown "ask again" and "cancel
        // the request" together: two opposite exits from the same dead end,
        // and the one carrying the word she was looking for pointed at a
        // request the server had already closed.
        if (request.isOpen) {
            Spacer(Modifier.height(Spacing.sm))
            SecondaryAction(
                label = strings["ride.action.cancel"],
                onClick = { onEvent(OffersEvent.Cancel) },
                enabled = !state.isCancelling && state.acceptingOfferId == null,
                modifier = Modifier.fillMaxWidth(),
            )
        }
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
                    "origin" to (request.originStationName ?: strings["common.value.unknown"]),
                    "destination" to (request.destinationName ?: strings["common.value.unknown"]),
                ],
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                strings[
                    "ride.offers.you_asked",
                    // The whole journey. Showing the outbound leg here
                    // told a passenger who had offered 300 out and 250
                    // back that they had offered 300.
                    "amount" to MoneyFormatter.format(request.askingTotal, strings),
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
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current
    val agrees = offer.agreesWith(asking)
    val difference = offer.differenceFrom(asking)

    VelroCard(modifier = modifier) {
        Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top,
            ) {
                Column(Modifier.weight(1f)) {
                    Text(
                        offer.driverName ?: strings["common.value.no_name"],
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
                                modifier = Modifier.size(Sizing.iconSm),
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
                        MoneyFormatter.format(offer.total, strings),
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                    )
                    // The two legs under the total, because the total is what
                    // is being chosen between and the split is what was
                    // argued. Only on a round trip: on a one-way journey the
                    // total is the only number there is.
                    offer.returnAmount?.let { back ->
                        Text(
                            strings["ride.offers.leg_out"] + " " +
                                MoneyFormatter.format(offer.amount, strings) + "  ·  " +
                                strings["ride.offers.leg_back"] + " " +
                                MoneyFormatter.format(back, strings),
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
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
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

/**
 * The request ended without a ride.
 *
 * Expired, or cancelled from another device. Either way there is nothing left
 * to wait for, and the passenger needs a way back to asking rather than a
 * spinner and a dead end.
 */
@Composable
private fun RequestClosed(status: RideRequestStatus, onAskAgain: () -> Unit) {
    val strings = LocalVelroStrings.current
    val expired = status == RideRequestStatus.EXPIRED
    Column(
        Modifier.fillMaxWidth().padding(vertical = Spacing.xl),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(Spacing.md),
    ) {
        Text(
            strings[
                if (expired) "ride.offers.expired_title"
                else "ride.offers.cancelled_title"
            ],
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            strings[
                if (expired) "ride.offers.expired_body"
                else "ride.offers.cancelled_body"
            ],
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            textAlign = TextAlign.Center,
        )
        PrimaryAction(
            label = strings["ride.offers.ask_again"],
            onClick = onAskAgain,
        )
    }
}
