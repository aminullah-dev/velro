package af.velro.feature.driver

import af.velro.core.i18n.Calendars
import af.velro.core.i18n.MoneyFormatter
import af.velro.core.i18n.Numerals
import af.velro.core.ui.component.DriverSummary
import af.velro.core.ui.component.ErrorState
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.component.StatusChip
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.component.messageKey
import af.velro.core.ui.component.tone
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import af.velro.domain.TripStatus
import af.velro.domain.VehicleStatus
import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
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
    viewModel: DriverHomeViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    DriverHomeScreen(
        state, viewModel::onEvent,
        onOpenDocuments = onOpenDocuments,
        onOpenVehicle = onOpenVehicle,
    )
}

@Composable
fun DriverHomeScreen(
    state: DriverHomeUiState,
    onEvent: (DriverHomeEvent) -> Unit,
    onOpenDocuments: () -> Unit = {},
    onOpenVehicle: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current

    if (state.isLoading) {
        LoadingState(modifier)
        return
    }
    if (state.profile == null) {
        ErrorState(
            errorCode = state.errorCode ?: "INTERNAL_ERROR",
            context = state.errorContext,
            onRetry = { onEvent(DriverHomeEvent.Refresh) },
        )
        return
    }

    Column(
        modifier
            .fillMaxSize()
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
            .imePadding()
            .padding(horizontal = Spacing.gutter, vertical = Spacing.lg)
    ) {
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
                Text(
                    strings["empty.trips"],
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        Spacer(Modifier.height(Spacing.xl))
        Earnings(state)
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
private fun Earnings(state: DriverHomeUiState) {
    val strings = LocalVelroStrings.current
    val earnings = state.earnings ?: return

    VelroCard {
        Column {
            Text(strings["earnings.title"], style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(Spacing.md))
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
