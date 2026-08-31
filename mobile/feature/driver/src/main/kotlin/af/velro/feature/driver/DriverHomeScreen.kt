package af.velro.feature.driver

import af.velro.core.i18n.Calendars
import af.velro.core.i18n.MoneyFormatter
import af.velro.core.i18n.Numerals
import af.velro.core.ui.component.DriverSummary
import af.velro.core.ui.component.BrandHeader
import af.velro.core.ui.theme.VelroColors
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
import af.velro.domain.MoneyValue
import af.velro.domain.TripStatus
import af.velro.domain.VehicleStatus
import androidx.compose.foundation.layout.Arrangement
import android.content.Context
import android.media.RingtoneManager
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import af.velro.domain.RideRequest
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.RadioButton
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.TextButton
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.Logout
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.LayoutDirection
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

    // The effects channel had no collector at all until now -- PassengerBoarded
    // has been fired into nothing since it was written. Which also means this
    // is the first time anything on the driver's handset makes a noise.
    val context = LocalContext.current
    val strings = LocalVelroStrings.current
    val snackbar = remember { SnackbarHostState() }
    LaunchedEffect(Unit) {
        viewModel.effects.collect { effect ->
            when (effect) {
                is DriverHomeEffect.RequestsArrived -> {
                    // Sound and vibration, because a driver waiting for work is
                    // not staring at the screen -- he is parked, talking, or
                    // watching the road. There is no push transport, so this is
                    // the only thing that can reach him, and it only works
                    // while the app is open. That limit is real and not
                    // something this file can fix.
                    ringOnce(context)
                    snackbar.showSnackbar(strings["driver.requests.arrived"])
                }
                is DriverHomeEffect.TripCompleted -> {
                    // Also never collected before now. A driver finished a
                    // journey and the app said nothing about what he had
                    // earned for it.
                    snackbar.showSnackbar(
                        effect.earning?.let {
                            strings[
                                "driver.trip.completed",
                                "amount" to MoneyFormatter.format(it, strings),
                            ]
                        } ?: strings["driver.trip.completed_plain"]
                    )
                }
                is DriverHomeEffect.PassengerBoarded -> {
                    snackbar.showSnackbar(
                        effect.name?.let {
                            strings["driver.verify.boarded_named", "name" to it]
                        } ?: strings["driver.verify.boarded"]
                    )
                }
            }
        }
    }

    DriverHomeScreen(
        state, viewModel::onEvent,
        snackbarHost = snackbar,
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
    snackbarHost: SnackbarHostState? = null,
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
                    // His own sheet: the number he would read out is his own.
                    driverPhone = null,
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

    // Both of these go through the frame, like every other screen.
    //
    // They used to be bare Columns on a 16dp pad with no bar and no gutter, so
    // a driver's very first screen -- the apply form, before he is a driver at
    // all -- sat on a different grid from everything he would see afterwards,
    // and the loading state jumped sideways the moment the profile arrived.
    // The big help button stays here rather than moving to the bar: there is
    // nothing on these screens for it to compete with, and it is the case it
    // was written for.
    if (state.isLoading) {
        VelroScreen(title = strings["driver.nav.home"], modifier = modifier) {
            HelpButton { helpOpen = true }
            LoadingState()
        }
        return
    }
    if (state.profile == null) {
        VelroScreen(title = strings["driver.nav.home"], modifier = modifier) {
            HelpButton { helpOpen = true }
            if (state.errorCode == "PERMISSION_DENIED") {
                // Not a failure: this is everybody's first minute in the app.
                //
                // GET driver/me is behind require_driver, so a person who has
                // just installed VELRO Driver and signed in gets a 403 -- and
                // this branch showed them "you do not have permission to do
                // this" over a Retry button that retries a 403 for ever. The
                // apply form was only reachable from a screen that needs the
                // profile this call could not return, so nobody could become a
                // VELRO driver through the driver app at all. Every driver in
                // the database was put there by the seed or by an operator.
                BecomeADriver(onOpenDocuments)
            } else {
                // The genuine failure: no signal, or the server is down.
                // Retry is the right offer, and the help button above it is
                // why this branch is not just an ErrorState -- a driver with
                // no data still needs an emergency number.
                ErrorState(
                    errorCode = state.errorCode ?: "INTERNAL_ERROR",
                    context = state.errorContext,
                    onRetry = { onEvent(DriverHomeEvent.Refresh) },
                )
            }
        }
        return
    }

    VelroScreen(
        title = strings["driver.nav.home"],
        snackbarHost = snackbarHost,
        // The brand header carries the title, the controls and the greeting,
        // so the frame must not draw a second bar above it.
        header = {
            BrandHeader(
                title = strings["app.name"],
                subtitle = state.profile?.fullName?.let {
                    strings["driver.greeting", "name" to it]
                } ?: strings["driver.greeting_no_name"],
                actions = {
                    TextButton(
                        onClick = { helpOpen = true },
                        colors = ButtonDefaults.textButtonColors(
                            // The field these sit on is constant, so
                            // its foreground is too. onPrimary is the
                            // near-black Green900 after dark: 1.91:1
                            // on the header, which is a help button
                            // nobody can find in the dark.
                            contentColor = VelroColors.OnBrandField,
                        ),
                    ) { Text(strings["safety.title"]) }
                    IconButton(onClick = { signingOut = true }) {
                        Icon(
                            Icons.AutoMirrored.Filled.Logout,
                            contentDescription = strings["auth.action.sign_out"],
                            tint = VelroColors.OnBrandField,
                        )
                    }
                },
            )
        },
        modifier = modifier,
    ) {
        // The greeting moved into the header, so this is the vehicle alone.
        DriverSummary(state.profile!!)

        // His papers and his vehicle, reachable once he is approved.
        //
        // Both doors existed only inside the PendingApproval and BecomeADriver
        // branches -- that is, only while `canWork` was false. The moment a
        // driver was approved they closed behind him: he could not look at his
        // own licence, could not re-upload one that was about to expire, and
        // could not correct the vehicle a passenger is told to look for. The
        // expiry warning itself lives on the documents screen, so the driver
        // it is written for was the one driver who could never see it.
        Spacer(Modifier.height(Spacing.sm))
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
        ) {
            SecondaryAction(
                label = strings["driver.documents.title"],
                onClick = onOpenDocuments,
                modifier = Modifier.weight(1f),
            )
            SecondaryAction(
                label = strings["driver.vehicle.title"],
                onClick = onOpenVehicle,
                modifier = Modifier.weight(1f),
            )
        }

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

                // The work, not a door to it. This was a single button
                // labelled "waiting passengers", so a driver sitting online
                // with somebody offering 200 afghani two miles away saw a
                // green rectangle and no reason to press it. Nothing rings on
                // this handset -- there is no push transport -- so if the
                // screen does not say it, he does not know it.
                if (state.waiting.isEmpty()) {
                    Text(
                        strings["driver.requests.none"],
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                } else {
                    for (request in state.waiting.take(3)) {
                        WaitingRequest(request, onOpenBoard)
                        Spacer(Modifier.height(Spacing.sm))
                    }
                }

                Spacer(Modifier.height(Spacing.sm))
                // Emphasis follows whether there is anything to act on. As an
                // unconditional PrimaryAction this was a full-width green
                // button sitting directly under the sentence "nobody is
                // waiting right now" -- the only primary action on the screen,
                // pointing at an empty list.
                if (state.waiting.isEmpty()) {
                    SecondaryAction(
                        label = strings["driver.board.title"],
                        onClick = onOpenBoard,
                        modifier = Modifier.fillMaxWidth(),
                    )
                } else {
                    PrimaryAction(
                        label = strings["driver.board.title"],
                        onClick = onOpenBoard,
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
            // Offline. This branch did not exist, so the screen fell through to
            // earnings and said nothing -- a driver could sit on it while a
            // passenger waited at a station, with no way to learn that the
            // switch above was the only thing between them.
            else -> OfflineNotice(state.waiting.size)
        }

        Spacer(Modifier.height(Spacing.xl))
        Earnings(state, onOpenEarnings)
    }
}

/**
 * One waiting passenger, on the driver's own home screen.
 *
 * The fare is the loudest thing on it deliberately: what a driver decides
 * with is the money and the road, in that order, and both have to survive
 * being read at arm's length in a parked car in sunlight.
 */
@Composable
private fun WaitingRequest(request: RideRequest, onOpen: () -> Unit) {
    val strings = LocalVelroStrings.current
    VelroCard(Modifier.fillMaxWidth().clickable { onOpen() }) {
        Column {
            Text(
                MoneyFormatter.format(request.askingTotal, strings),
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary,
            )
            Spacer(Modifier.height(Spacing.xxs))
            Text(
                strings[
                    "ride.journey.from_to",
                    "origin" to (request.originStationName
                        ?: strings["common.value.unknown"]),
                    "destination" to (request.destinationName
                        ?: strings["common.value.unknown"]),
                ],
                style = MaterialTheme.typography.bodyMedium,
            )
            // Same reason as the board: a request is no longer always "now",
            // so the preview on his own home screen has to say when.
            request.requestedFor?.let { departure ->
                Spacer(Modifier.height(Spacing.xxs))
                Text(
                    Calendars.dateTime(departure, strings.locale),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.secondary,
                )
            }
            request.returnFor?.let { back ->
                Text(
                    strings["ride.return.label"] + ": " +
                        Calendars.dateTime(back, strings.locale),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.secondary,
                )
            }
            if (request.alreadyOffered) {
                Spacer(Modifier.height(Spacing.xxs))
                Text(
                    strings["driver.board.already_offered"],
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

/**
 * What an offline driver is told.
 *
 * The count is the part that matters. "You are offline" is a status and
 * invites nothing; "someone is waiting right now" is a reason, and it is true
 * or it is absent -- never a decoration.
 */
@Composable
private fun OfflineNotice(waitingCount: Int) {
    val strings = LocalVelroStrings.current
    VelroCard {
        Column {
            Text(
                strings["driver.offline.title"],
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(Spacing.xs))
            Text(
                strings["driver.offline.body"],
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            if (waitingCount > 0) {
                Spacer(Modifier.height(Spacing.sm))
                Text(
                    strings["driver.offline.waiting"],
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
        }
    }
}

/**
 * The first screen of a driver's life with VELRO.
 *
 * Deliberately not an error page: nothing has gone wrong, the person simply
 * does not drive for VELRO yet. It says what applying involves, because the
 * next screen asks for a tazkira and a licence and a jawaz-e-sair, and finding
 * that out after tapping is worse than being told.
 */
@Composable
private fun BecomeADriver(onOpenDocuments: () -> Unit) {
    val strings = LocalVelroStrings.current
    Column(Modifier.fillMaxWidth()) {
        Text(
            strings["driver.welcome.title"],
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(Spacing.sm))
        Text(
            strings["driver.welcome.body"],
            style = MaterialTheme.typography.bodyLarge,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(Spacing.lg))
        PrimaryAction(
            label = strings["driver.documents.apply"],
            onClick = onOpenDocuments,
            modifier = Modifier.fillMaxWidth(),
        )
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
    val context = LocalContext.current
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
            // Where to drive. Until now the card showed a trip number, a
            // clock time and a head count, and he could not tell the station
            // he was meant to be at.
            val origin = trip.originStationName
            val destination = trip.destinationName
            if (origin != null && destination != null) {
                Spacer(Modifier.height(Spacing.xs))
                Text(
                    strings[
                        "ride.journey.from_to",
                        "origin" to origin,
                        "destination" to destination,
                    ],
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Medium,
                )
            }

            Spacer(Modifier.height(Spacing.sm))
            for (rider in assignment.manifest) {
                // Who to look for, and what to collect from them. The booking
                // number is what he calls out at the station and what the
                // passenger already has on her own screen -- it identifies one
                // rider out of three, which a name he was never given cannot.
                Text(
                    strings["booking.label.number"],
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                    Text(rider.number, style = MaterialTheme.typography.bodyMedium)
                }
                rider.fareTotalMinor?.let { minor ->
                    Text(
                        MoneyFormatter.format(
                            MoneyValue(minor.toLong(), rider.fareCurrency ?: "AFN"), strings,
                        ),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                    )
                }
                rider.passengerPhone?.let { phone ->
                    SecondaryAction(
                        label = strings["driver.action.call_passenger"],
                        onClick = { context.dialNumber(phone) },
                        modifier = Modifier.fillMaxWidth(),
                    )
                }
            }
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
                // What he can take out today, at the size it matters.
                //
                // All three figures were the same weight in the same size, so
                // the number a driver opens this card to read sat level with
                // his lifetime total and his trip count. A summary with no
                // hierarchy is a table, and he has to read all of it to find
                // the one line he came for.
                //
                // A negative balance is not a small available balance: on a
                // cash trip the driver already took the fare at the roadside,
                // so VELRO's share is money he is holding for us. Calling that
                // "available" and printing it in the take-your-money green,
                // which is what this card did, tells him the opposite of what
                // is true about his own wallet. The two words for it already
                // existed -- they were only ever used on the earnings screen
                // behind this card.
                // The wallet's whole position, not just the free part.
                //
                // Asking a settlement to be opened moves the debt out of
                // `available` and into `pending`, so this card -- which read
                // `available` alone -- went from "you owe VELRO 7" to
                // "withdrawable: 0" the moment the driver acted on it, while
                // the earnings screen one tap behind still showed the seven.
                // Two screens disagreeing about a man's own money is worse
                // than either of them being wrong on its own.
                val owes = earnings.owesPlatform
                val headline = earnings.headlineAmount
                Text(
                    if (owes) strings["driver.earnings.owed"]
                    else strings["earnings.label.available"],
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(
                    MoneyFormatter.format(headline, strings),
                    style = MaterialTheme.typography.displaySmall,
                    fontWeight = FontWeight.Bold,
                    color =
                        if (owes) MaterialTheme.colorScheme.error
                        else MaterialTheme.colorScheme.primary,
                )
                if (owes) {
                    Spacer(Modifier.height(Spacing.xs))
                    Text(
                        strings["driver.earnings.owed_explained"],
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Spacer(Modifier.height(Spacing.md))
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

/**
 * Open the dialler with a number in it.
 *
 * ACTION_DIAL, never ACTION_CALL: no CALL_PHONE permission, and the app never
 * places a call the person did not see. The <queries> block both manifests
 * gained for the safety sheet is what makes this resolve at all.
 */
private fun android.content.Context.dialNumber(number: String) {
    runCatching {
        startActivity(
            android.content.Intent(
                android.content.Intent.ACTION_DIAL,
                android.net.Uri.parse("tel:$number"),
            ).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }
}


/**
 * A short sound and a buzz, once.
 *
 * The system notification tone rather than a bundled sound file: a driver in
 * Ghorband has already chosen a volume he can hear over a Corolla engine, and
 * an app that ships its own tone ignores that choice. RingtoneManager also
 * respects silent mode, which a raw MediaPlayer would not -- if he has
 * silenced the phone he meant it, and the vibration still reaches him.
 */
private fun ringOnce(context: Context) {
    runCatching {
        RingtoneManager
            .getRingtone(
                context,
                RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION),
            )
            ?.play()
    }
    runCatching {
        val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            (context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE)
                as VibratorManager).defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
        }
        vibrator.vibrate(
            VibrationEffect.createOneShot(400, VibrationEffect.DEFAULT_AMPLITUDE)
        )
    }
}
