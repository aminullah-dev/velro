package af.velro.feature.driver

import af.velro.core.i18n.Calendars
import af.velro.core.i18n.MoneyFormatter
import af.velro.core.i18n.Numerals
import af.velro.core.ui.component.DriverSummary
import af.velro.core.ui.component.ErrorState
import af.velro.core.ui.component.ConfirmDialog
import af.velro.core.ui.component.VelroScreen
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.component.StatusChip
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.component.messageKey
import af.velro.core.ui.component.tone
import af.velro.feature.safety.HelpSheet
import af.velro.feature.safety.RideFacts
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import af.velro.domain.TripStatus
import af.velro.domain.VehicleStatus
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.RadioButton
import androidx.compose.material3.TextButton
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextAlign
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun DriverHomeRoute(
    onOpenDocuments: () -> Unit,
    onOpenVehicle: () -> Unit,
    onOpenEarnings: () -> Unit,
    onOpenBoard: () -> Unit,
    onOpenReports: () -> Unit,
    onSignOut: () -> Unit,
    viewModel: DriverHomeViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    DriverHomeScreen(
        state, viewModel::onEvent,
        onOpenDocuments = onOpenDocuments,
        onOpenVehicle = onOpenVehicle,
        onOpenEarnings = onOpenEarnings,
        onOpenReports = onOpenReports,
        onSignOut = onSignOut,
        onOpenBoard = onOpenBoard,
    )
}

@Composable
fun DriverHomeScreen(
    state: DriverHomeUiState,
    onEvent: (DriverHomeEvent) -> Unit,
    onOpenDocuments: () -> Unit = {},
    onOpenVehicle: () -> Unit = {},
    onOpenEarnings: () -> Unit = {},
    onOpenBoard: () -> Unit = {},
    onOpenReports: () -> Unit = {},
    onSignOut: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current

    // Get help, above every early return.
    //
    // It used to sit at the foot of the screen, below the guards for loading
    // and for a null profile -- and DriverRepository.profile() is a bare
    // network call with no cache, so on any cold start without data the driver
    // got a full-screen Retry page and no help control at all. That is the
    // case ADR 0010 opens with: a driver alone on a mountain road at night.
    //
    // The sheet needs nothing from the profile: the numbers are compiled in
    // and `ride` is already null-safe.
    var helpOpen by remember { mutableStateOf(false) }
    var signingOut by remember { mutableStateOf(false) }
    if (signingOut) {
        // Confirmed because it wipes the local cache. On a handset shared
        // in a household that is right, and it is also unrecoverable
        // without a connection to sign back in.
        ConfirmDialog(
            titleKey = "auth.action.sign_out",
            bodyKey = "auth.sign_out_warning",
            confirmKey = "auth.action.sign_out",
            onConfirm = { signingOut = false; onSignOut() },
            onDismiss = { signingOut = false },
        )
    }
    if (helpOpen) {
        val assignment = state.assignment
        HelpSheet(
            ride = assignment?.let {
                RideFacts(
                    bookingNumber = it.trip.number,
                    driverName = state.profile?.fullName,
                    plate = state.profile?.vehicle?.plateNumber,
                    origin = null,
                    destination = null,
                )
            },
            tripId = assignment?.trip?.id,
            onOpenReports = onOpenReports,
            onDismiss = { helpOpen = false },
        )
    }

    if (state.isLoading) {
        Column(modifier.fillMaxSize().statusBarsPadding().padding(Spacing.lg)) {
            HelpButton { helpOpen = true }
            LoadingState()
        }
        return
    }
    if (state.profile == null) {
        // The offline case. The Retry page used to be the whole screen,
        // so a driver with no data had no way to an emergency number.
        Column(modifier.fillMaxSize().statusBarsPadding().padding(Spacing.lg)) {
            HelpButton { helpOpen = true }
            ErrorState(
                errorCode = state.errorCode ?: "INTERNAL_ERROR",
                context = state.errorContext,
                onRetry = { onEvent(DriverHomeEvent.Refresh) },
            )
        }
        return
    }

    VelroScreen(
        title = strings["driver.nav.home"],
        actions = {
            IconButton(onClick = { signingOut = true }) {
                Icon(
                    Icons.AutoMirrored.Filled.Logout,
                    contentDescription = strings["auth.action.sign_out"],
                )
            }
        },
        modifier = modifier,
    ) {
        // At the top, not the foot of a scroll. The moment it is needed
        // is the moment nobody scrolls.
        HelpButton { helpOpen = true }

        DriverSummary(state.profile!!)

        Spacer(Modifier.height(Spacing.lg))

        if (!state.canWork) {
            // Approval is a gate, not a label: explain it, and give the driver
            // the one action that moves them past it.
            PendingApproval(state, onOpenDocuments, onOpenVehicle)
        } else {
            OnlineToggle(state, onEvent)
        }

        if (state.errorCode != null) {
            InlineError(state.errorCode!!, context = state.errorContext)
        }

        // What the server has told this driver. Without it the only way to
        // learn that a bid was accepted is to notice a trip appear.
        Inbox(state, onEvent)

        Spacer(Modifier.height(Spacing.lg))

        val assignment = state.assignment
        when {
            assignment != null -> CurrentTrip(state, onEvent)
            state.offers.isNotEmpty() -> Offers(state, onEvent)
            state.isOnline -> {
                Text(
                    strings["driver.section.requests"],
                    style = MaterialTheme.typography.titleMedium,
                )
                Spacer(Modifier.height(Spacing.sm))
                // Section 89: work arrives as passengers naming a price, so the
                // board is the primary action for a driver who is online.
                PrimaryAction(
                    label = strings["driver.board.title"],
                    onClick = onOpenBoard,
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }

        Spacer(Modifier.height(Spacing.xl))
        Earnings(state, onOpenEarnings)
    }
}

@Composable
private fun PendingApproval(
    state: DriverHomeUiState,
    onOpenDocuments: () -> Unit,
    onOpenVehicle: () -> Unit,
) {
    val strings = LocalVelroStrings.current
    VelroCard {
        Column {
            Text(
                strings["driver.pending.title"],
                style = MaterialTheme.typography.titleMedium,
            )
            Spacer(Modifier.height(Spacing.sm))
            Text(
                strings["driver.pending.body"],
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            val missing = state.profile?.missingDocuments.orEmpty()
            if (missing.isNotEmpty()) {
                Spacer(Modifier.height(Spacing.sm))
                // Names the documents, so the driver knows what to bring rather
                // than being told only that something is wrong.
                Text(
                    missing.joinToString(" • ") {
                        strings["document.type.${it.lowercase()}"]
                    },
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.secondary,
                )
            }
            val needsVehicle = state.profile?.blockedByVehicle == true
            if (needsVehicle) {
                Spacer(Modifier.height(Spacing.sm))
                Text(
                    strings[
                        when (state.profile?.vehicle?.status) {
                            null -> "driver.vehicle.none"
                            VehicleStatus.SUSPENDED -> "driver.vehicle.suspended"
                            else -> "driver.vehicle.awaiting"
                        }
                    ],
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.secondary,
                )
            }
            Spacer(Modifier.height(Spacing.md))
            // Two gates, two screens. Offer whichever one the driver can act on
            // -- sending them to the documents screen over a missing car is the
            // fastest way to make a working app feel broken.
            SecondaryAction(
                label = strings["driver.documents.title"],
                onClick = onOpenDocuments,
            )
            if (needsVehicle) {
                Spacer(Modifier.height(Spacing.sm))
                SecondaryAction(
                    label = strings["driver.vehicle.title"],
                    onClick = onOpenVehicle,
                )
            }
        }
    }
}

@Composable
private fun OnlineToggle(state: DriverHomeUiState, onEvent: (DriverHomeEvent) -> Unit) {
    val strings = LocalVelroStrings.current
    VelroCard {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                strings[if (state.isOnline) "driver.status.online" else "driver.status.offline"],
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                color = if (state.isOnline) MaterialTheme.colorScheme.primary
                else MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Switch(
                checked = state.isOnline,
                onCheckedChange = { onEvent(DriverHomeEvent.ToggleOnline) },
                enabled = !state.isBusy,
            )
        }
    }
}

@Composable
private fun Offers(state: DriverHomeUiState, onEvent: (DriverHomeEvent) -> Unit) {
    val strings = LocalVelroStrings.current
    Text(strings["driver.section.requests"], style = MaterialTheme.typography.titleMedium)
    Spacer(Modifier.height(Spacing.sm))

    for (offer in state.offers) {
        VelroCard {
            Column {
                Text(
                    Calendars.time(offer.scheduledDepartureAt, strings.locale),
                    style = MaterialTheme.typography.titleLarge,
                )
                Spacer(Modifier.height(Spacing.sm))
                Text(
                    strings["driver.label.passengers"] + ": " +
                        Numerals.localise(
                            (offer.seatCapacity - offer.seatsAvailable).toString(),
                            strings.locale,
                        ),
                    style = MaterialTheme.typography.bodyMedium,
                )
                Spacer(Modifier.height(Spacing.md))
                PrimaryAction(
                    label = strings["driver.action.accept"],
                    onClick = { onEvent(DriverHomeEvent.AcceptOffer(offer.id)) },
                    enabled = !state.isBusy,
                )
            }
        }
        Spacer(Modifier.height(Spacing.sm))
    }
}

/**
 * The trip in flight.
 *
 * Exactly one forward action is offered, derived from the transition table, so
 * a driver never has to choose between buttons or discover that one of them is
 * refused.
 */
@Composable
private fun CurrentTrip(state: DriverHomeUiState, onEvent: (DriverHomeEvent) -> Unit) {
    val strings = LocalVelroStrings.current
    val assignment = state.assignment ?: return
    val trip = assignment.trip

    VelroCard {
        Column {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(trip.number, style = MaterialTheme.typography.bodyMedium)
                StatusChip(trip.status.messageKey(), trip.status.tone())
            }

            Spacer(Modifier.height(Spacing.md))

            Text(
                Calendars.time(trip.scheduledDepartureAt, strings.locale),
                style = MaterialTheme.typography.titleLarge,
            )
            Text(
                strings["driver.label.passengers"] + ": " +
                    Numerals.localise(assignment.manifest.size.toString(), strings.locale),
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }

    if (state.canVerifyPassenger) {
        Spacer(Modifier.height(Spacing.lg))
        VerifyPassenger(state, onEvent)
    }

    val next = state.nextStep
    if (next != null) {
        Spacer(Modifier.height(Spacing.lg))
        PrimaryAction(
            label = strings[next.actionKey()],
            onClick = { onEvent(DriverHomeEvent.AdvanceTrip) },
            enabled = !state.isBusy,
            loading = state.isBusy,
        )
    }

    // The way out. A driver whose car breaks down at a pickup point had no
    // action here at all -- the API accepted CANCELLED and the app only ever
    // walked forward, so the choice was drive the trip or abandon the
    // passenger silently. Secondary and below the forward action, because
    // cancelling is the exception.
    if (state.canCancelTrip) {
        var choosing by remember { mutableStateOf(false) }
        Spacer(Modifier.height(Spacing.sm))
        SecondaryAction(
            label = strings["driver.trip.cancel"],
            onClick = { choosing = true },
            enabled = !state.isBusy,
            modifier = Modifier.fillMaxWidth(),
        )
        if (choosing) {
            CancelTripDialog(
                onDismiss = { choosing = false },
                onConfirm = { reason ->
                    choosing = false
                    onEvent(DriverHomeEvent.CancelTrip(reason, null))
                },
            )
        }
    }
}

/**
 * Why the trip is being called off.
 *
 * A reason is asked for rather than optional: a cancellation with none cannot
 * be told from any other, and a driver whose car broke down and one who simply
 * changed their mind look identical in the report afterwards. The list is the
 * reason codes the server accepts, so the app cannot offer one that fails.
 */
@Composable
private fun CancelTripDialog(onDismiss: () -> Unit, onConfirm: (String) -> Unit) {
    val strings = LocalVelroStrings.current
    val reasons = listOf("VEHICLE_PROBLEM", "WEATHER", "DRIVER_CANCELLED", "OTHER")
    var chosen by remember { mutableStateOf(reasons.first()) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(strings["driver.trip.cancel_title"]) },
        text = {
            Column {
                Text(
                    strings["driver.trip.cancel_hint"],
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(Spacing.md))
                for (reason in reasons) {
                    Row(
                        Modifier
                            .fillMaxWidth()
                            .clickable { chosen = reason }
                            .padding(vertical = Spacing.sm),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        RadioButton(selected = chosen == reason, onClick = { chosen = reason })
                        Spacer(Modifier.width(Spacing.sm))
                        Text(strings["cancel.reason.${reason.lowercase()}"])
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = { onConfirm(chosen) }) {
                Text(strings["driver.trip.cancel_confirm"])
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text(strings["common.action.cancel"]) }
        },
    )
}

/**
 * The label for the button that moves the trip to [this] status.
 *
 * It names what tapping *does*, not the state being left. Getting this wrong is
 * how the same words ended up on three controls at once on the boarding screen.
 */
private fun TripStatus.actionKey(): String = when (this) {
    TripStatus.DRIVER_ARRIVING -> "driver.action.on_my_way"
    TripStatus.ARRIVED_AT_PICKUP -> "driver.action.arrived"
    TripStatus.BOARDING -> "driver.action.start_boarding"
    TripStatus.IN_TRANSIT -> "driver.action.start_trip"
    TripStatus.ARRIVED -> "driver.action.arrived_destination"
    TripStatus.COMPLETED -> "driver.action.complete_trip"
    else -> "common.action.confirm"
}

@Composable
private fun VerifyPassenger(state: DriverHomeUiState, onEvent: (DriverHomeEvent) -> Unit) {
    val strings = LocalVelroStrings.current
    VelroCard {
        Column {
            Text(
                strings["driver.action.verify_passenger"],
                style = MaterialTheme.typography.titleMedium,
            )
            Spacer(Modifier.height(Spacing.md))
            OutlinedTextField(
                value = state.verifyingCode,
                onValueChange = { onEvent(DriverHomeEvent.VerifyCodeChanged(it.uppercase())) },
                singleLine = true,
                // The code is alphanumeric and read aloud or shown on a screen;
                // upper case avoids the driver hunting for the shift key.
                keyboardOptions = KeyboardOptions(
                    capitalization = KeyboardCapitalization.Characters,
                ),
                textStyle = MaterialTheme.typography.titleLarge.copy(
                    textAlign = TextAlign.Center,
                ),
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(Spacing.md))
            SecondaryAction(
                label = strings["driver.action.verify_passenger"],
                onClick = { onEvent(DriverHomeEvent.VerifyPassenger) },
                enabled = state.verifyingCode.length >= 3 && !state.isBusy,
            )
            if (state.lastVerified != null) {
                Spacer(Modifier.height(Spacing.sm))
                Text(
                    state.lastVerified!! + " ✓",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
        }
    }
}

@Composable
private fun Earnings(state: DriverHomeUiState, onOpenEarnings: () -> Unit) {
    val strings = LocalVelroStrings.current
    // Not an early return. The earnings card used to open with
    // `state.earnings ?: return`, which took the section's only navigation
    // button with it -- so an approved, offline driver whose earnings call
    // failed was left on a screen with exactly one control, the online switch,
    // and nothing explaining why.
    val earnings = state.earnings

    VelroCard {
        Column {
            Text(strings["earnings.title"], style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(Spacing.md))
            if (earnings == null) {
                // The figures did not load. Say so rather than showing zeroes,
                // which a driver would read as "I earned nothing today".
                Text(
                    strings["common.state.loading"],
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } else {
                EarningRow(strings["earnings.label.available"], earnings.available.let {
                    MoneyFormatter.format(it, strings)
                })
                EarningRow(strings["earnings.label.lifetime"], earnings.lifetimeEarned.let {
                    MoneyFormatter.format(it, strings)
                })
                EarningRow(
                    strings["earnings.label.trips"],
                    Numerals.localise(earnings.completedTrips.toString(), strings.locale),
                )
            }
            Spacer(Modifier.height(Spacing.md))
            // The card is a summary; the ledger and payouts live behind it.
            SecondaryAction(
                label = strings["driver.earnings.title"],
                onClick = onOpenEarnings,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

@Composable
private fun EarningRow(label: String, value: String) {
    Row(
        Modifier.fillMaxWidth().padding(vertical = Spacing.xs),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(
            label,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(value, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium)
    }
}

/**
 * What the server has told this driver.
 *
 * There is no push transport, so this list is the only way a driver learns that
 * a passenger accepted their bid -- and until it existed the screen loaded once
 * and never again, so the driver found out by noticing a trip appear, if they
 * happened to look.
 *
 * Unread only, and tapping clears them: this is a notice, not an archive.
 */
@Composable
private fun Inbox(state: DriverHomeUiState, onEvent: (DriverHomeEvent) -> Unit) {
    val strings = LocalVelroStrings.current
    val unread = state.inbox?.notifications?.filter { it.isUnread }.orEmpty()
    if (unread.isEmpty()) return

    Spacer(Modifier.height(Spacing.md))
    VelroCard {
        Column {
            for (notification in unread.take(3)) {
                Text(
                    strings[notification.messageKey, notification.payload],
                    style = MaterialTheme.typography.bodyMedium,
                )
                Spacer(Modifier.height(Spacing.xs))
            }
            Spacer(Modifier.height(Spacing.sm))
            SecondaryAction(
                // Not "Close": this marks every message read and they do
                // not come back. The label has to say so.
                label = strings["inbox.mark_read"],
                onClick = { onEvent(DriverHomeEvent.MarkNotificationsRead) },
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

/**
 * The way to the emergency numbers, rendered in every state of the screen.
 *
 * Loading, failed, and working all show it. A driver who cannot reach 119
 * because a profile request timed out is the failure this feature was written
 * to prevent, and for a while it was the failure this screen shipped.
 */
@Composable
private fun HelpButton(onClick: () -> Unit) {
    val strings = LocalVelroStrings.current
    SecondaryAction(
        label = strings["safety.title"],
        onClick = onClick,
        modifier = Modifier.fillMaxWidth(),
    )
    Spacer(Modifier.height(Spacing.md))
}
