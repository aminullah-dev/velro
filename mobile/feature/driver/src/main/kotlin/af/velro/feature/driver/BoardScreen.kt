package af.velro.feature.driver

import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import af.velro.core.i18n.MoneyFormatter
import af.velro.core.i18n.Calendars
import af.velro.core.i18n.Numerals
import af.velro.core.ui.component.EmptyState
import af.velro.core.ui.component.ErrorState
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.component.VelroScreen
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import af.velro.domain.MoneyValue
import af.velro.domain.RideRequest
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun BoardRoute(
    onBack: () -> Unit = {},
    viewModel: BoardViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    BoardScreen(state, viewModel::onEvent, onBack = onBack)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BoardScreen(
    state: BoardUiState,
    onEvent: (BoardEvent) -> Unit,
    onBack: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current

    if (state.isLoading && state.requests.isEmpty()) {
        LoadingState(modifier.fillMaxSize())
        return
    }
    if (state.requests.isEmpty() && state.errorCode != null) {
        ErrorState(
            errorCode = state.errorCode!!,
            context = state.errorContext,
            onRetry = { onEvent(BoardEvent.Refresh) },
            modifier = modifier.fillMaxSize(),
        )
        return
    }

    // This screen owns a LazyColumn, so the frame must not scroll for it.
    // Without this the board crashed outright -- a lazy list inside a
    // verticalScroll is measured with infinite height, which Compose refuses.
    // It never showed up in testing because the crash needs a request to be
    // waiting: with an empty board the other branch renders an EmptyState and
    // nothing is nested. So the driver's board worked perfectly until the
    // moment somebody actually wanted a car, and then it killed the app.
    VelroScreen(
        title = strings["driver.board.title"],
        onBack = onBack,
        scrollable = false,
        modifier = modifier,
    ) {
        // One spacer, matching the offers and reports screens it sits beside.
        // Two were left behind when the in-content heading was deleted, so the
        // board started its content 8dp lower than its siblings.
        Spacer(Modifier.height(Spacing.md))

        if (state.errorCode != null && state.offeringOn == null) {
            InlineError(state.errorCode!!, context = state.errorContext)
        }

        // Pull to refresh. The board polls, but a driver who has just gone
        // online wants to know the list in front of him is this second's, not
        // up to ten seconds old, and `Refresh` was reachable only from the
        // error state.
        PullToRefreshBox(
            isRefreshing = state.isRefreshing,
            onRefresh = { onEvent(BoardEvent.PullToRefresh) },
            modifier = Modifier.fillMaxSize(),
        ) {
        if (state.requests.isEmpty()) {
            EmptyState(messageKey = "driver.board.empty")
        } else {
            LazyColumn(
                verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                modifier = Modifier.fillMaxSize(),
            ) {
                items(state.requests, key = { it.id }) { request ->
                    RequestCard(
                        // This board moves on its own, in both directions:
                        // requests arrive, and they leave when another driver
                        // wins them or they expire. Without an animation the
                        // card a driver is reaching for is simply replaced by
                        // a different journey at the same coordinates, and he
                        // bids on a route he never chose.
                        modifier = Modifier.animateItem(),
                        request = request,
                        // His own price for the whole journey. Passing
                        // the outbound alone told a driver who had just
                        // offered 350 and 300 that he had offered 350.
                        myOffer = state.myOfferOn(request.id)?.total,
                        busy = state.busyRequestId == request.id,
                        onOffer = { onEvent(BoardEvent.StartOffering(request.id)) },
                        onWithdraw = {
                            state.myOfferOn(request.id)?.let {
                                onEvent(BoardEvent.Withdraw(it.id))
                            }
                        },
                    )
                }
            }
        }
        }
    }

    val offering = state.offeringOn?.let { id -> state.requests.firstOrNull { it.id == id } }
    if (offering != null) {
        ModalBottomSheet(
            onDismissRequest = { onEvent(BoardEvent.StopOffering) },
            sheetState = rememberModalBottomSheetState(),
        ) {
            OfferSheet(
                request = offering,
                busy = state.busyRequestId == offering.id,
                errorCode = state.errorCode,
                errorContext = state.errorContext,
                onSend = { amount, returnAmount, note ->
                    onEvent(BoardEvent.Offer(offering.id, amount, returnAmount, note))
                },
            )
        }
    }
}

@Composable
private fun RequestCard(
    request: RideRequest,
    myOffer: MoneyValue?,
    busy: Boolean,
    onOffer: () -> Unit,
    onWithdraw: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current
    VelroCard(modifier = modifier) {
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
            // When he is being asked to drive.
            //
            // Every request used to mean "now", so a board card had nothing to
            // say about time and a driver bidding was only ever agreeing to
            // leave immediately. Now that a passenger can ask for six tomorrow
            // morning, a bid placed without seeing that is a bid placed blind.
            request.requestedFor?.let { departure ->
                Text(
                    strings["ride.when.departure"] + ": " +
                        Calendars.dateTime(departure, strings.locale),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.secondary,
                )
            }
            // The way back, if there is one.
            //
            // A driver naming a price without this is naming it for half the
            // job: in Ghorband the return is usually a different day, so it
            // means keeping the car free tomorrow as well.
            request.returnFor?.let { back ->
                Text(
                    strings["ride.return.label"] + ": " +
                        Calendars.dateTime(back, strings.locale),
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.secondary,
                )
            }
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    strings["ride.ask.passengers"] + " " +
                        Numerals.localise(request.passengerCount.toString(), strings.locale),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                // The number the driver is deciding about, given the weight it
                // deserves rather than buried in a line of detail.
                Text(
                    MoneyFormatter.format(request.askingTotal, strings),
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                )
            }
            // What is being asked each way. The headline is the journey; this
            // is the argument, and a driver answers it leg by leg.
            request.returnFare?.let { back ->
                Text(
                    strings["ride.offers.leg_out"] + " " +
                        MoneyFormatter.format(request.offeredFare, strings) +
                        "  \u00b7  " + strings["ride.offers.leg_back"] + " " +
                        MoneyFormatter.format(back, strings),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            request.note?.let {
                Text(
                    it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            Spacer(Modifier.height(Spacing.xs))
            if (myOffer != null) {
                // Already answered: show the number, and the way to change it.
                Text(
                    strings[
                        "driver.board.offered",
                        "amount" to MoneyFormatter.format(myOffer, strings),
                    ],
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.primary,
                    fontWeight = FontWeight.Medium,
                )
                Spacer(Modifier.height(Spacing.xs))
                SecondaryAction(
                    label = strings["driver.board.withdraw"],
                    onClick = onWithdraw,
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth(),
                )
            } else {
                PrimaryAction(
                    label = strings["driver.board.offer"],
                    onClick = onOffer,
                    enabled = !busy,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
    }
}

@Composable
private fun OfferSheet(
    request: RideRequest,
    busy: Boolean,
    errorCode: String?,
    errorContext: Map<String, Any?>,
    onSend: (Long, Long?, String?) -> Unit,
) {
    val strings = LocalVelroStrings.current
    var amount by remember(request.id) { mutableStateOf("") }
    var returnAmount by remember(request.id) { mutableStateOf("") }
    var note by remember(request.id) { mutableStateOf("") }

    val minor = amount.toLongOrNull()?.times(100)
    val returnMinor = returnAmount.toLongOrNull()?.times(100)
    // A return has to be priced when one was asked for. The server refuses an
    // answer that covers only half the journey, and so does this sheet.
    val wantsReturn = request.returnFare != null
    val returnReady = !wantsReturn || (returnMinor != null && returnMinor > 0)
    // Both legs together, which is what the passenger compares between drivers.
    val asking = request.askingTotal

    Column(
        Modifier
            .fillMaxWidth()
            .padding(horizontal = Spacing.gutter)
            // Scrolls, for the same reason the ask screen does: a sheet that
            // happens to fit is not a sheet that fits. Adding the return leg's
            // field and the total pushed "send my price" against the bottom
            // edge, clipped to a sliver -- the driver's only way to answer.
            .verticalScroll(rememberScrollState())
            // The keyboard must not cover the send button, and the sheet must
            // clear the gesture bar.
            .imePadding()
            .navigationBarsPadding()
            .padding(bottom = Spacing.lg),
        verticalArrangement = Arrangement.spacedBy(Spacing.sm),
    ) {
        Text(
            strings["driver.offer.title"],
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            strings["driver.offer.hint"],
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        // Agreeing to the asking price is one tap, because it is the common
        // answer. Typing the same number again would be a toll on the thing
        // most drivers want to do.
        SecondaryAction(
            label = strings[
                "driver.offer.match",
                "amount" to MoneyFormatter.format(asking, strings),
            ],
            // Matching the asking price means matching it leg for leg, so
            // the split the passenger asked for survives the one-tap answer.
            onClick = {
                onSend(
                    request.offeredFare.amountMinor,
                    request.returnFare?.amountMinor,
                    note.ifBlank { null },
                )
            },
            enabled = !busy,
            modifier = Modifier.fillMaxWidth(),
        )

        OutlinedTextField(
            value = amount,
            onValueChange = { amount = Numerals.latin(it).filter(Char::isDigit) },
            label = {
                Text(
                    if (wantsReturn) strings["ride.ask.fare_out"]
                    else strings["driver.offer.title"]
                )
            },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            modifier = Modifier.fillMaxWidth(),
        )
        if (wantsReturn) {
            OutlinedTextField(
                value = returnAmount,
                onValueChange = {
                    returnAmount = Numerals.latin(it).filter(Char::isDigit)
                },
                label = { Text(strings["ride.ask.fare_back"]) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                modifier = Modifier.fillMaxWidth(),
            )
            if (minor != null && returnMinor != null) {
                Text(
                    strings[
                        "ride.ask.fare_total",
                        "amount" to MoneyFormatter.format(
                            MoneyValue(minor + returnMinor, asking.currency), strings
                        ),
                    ],
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }
        OutlinedTextField(
            value = note,
            onValueChange = { note = it },
            label = { Text(strings["ride.ask.note"]) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        if (errorCode != null) {
            // The reason stays with the sheet: the driver's next move is to
            // change the number, and they cannot do that from a closed sheet.
            InlineError(errorCode, context = errorContext)
        }

        PrimaryAction(
            label = strings["driver.offer.send"],
            onClick = {
                minor?.let { onSend(it, if (wantsReturn) returnMinor else null, note.ifBlank { null }) }
            },
            enabled = minor != null && minor > 0 && returnReady && !busy,
            loading = busy,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}
