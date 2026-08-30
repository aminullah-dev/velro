package af.velro.feature.trip

import af.velro.core.i18n.Calendars
import af.velro.core.ui.component.BoardingCode
import af.velro.core.ui.component.ErrorState
import af.velro.core.ui.component.FareRow
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.component.StatusChip
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.component.messageKey
import af.velro.core.ui.component.tone
import af.velro.feature.safety.HelpSheet
import af.velro.feature.safety.RideFacts
import af.velro.core.ui.component.VelroScreen
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.StarBorder
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import af.velro.domain.Booking
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun BookingDetailRoute(
    onBack: () -> Unit = {},
    viewModel: BookingDetailViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    BookingDetailScreen(state, viewModel::onEvent, onBack = onBack)
}

@Composable
fun BookingDetailScreen(
    state: BookingDetailUiState,
    onEvent: (BookingDetailEvent) -> Unit,
    onBack: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current
    val booking = state.booking

    if (booking == null) {
        if (state.errorCode != null) {
            ErrorState(
                errorCode = state.errorCode!!,
                context = state.errorContext,
                onRetry = { onEvent(BookingDetailEvent.Refresh) },
            )
        } else {
            LoadingState()
        }
        return
    }

    VelroScreen(
        title = booking.number,
        onBack = onBack,
        modifier = modifier,
    ) {
        // The booking number is the app bar title now, so only the status
        // stays here -- and it keeps the row it needs to sit on its own line
        // rather than crowding the bar.
        StatusChip(booking.status.messageKey(), booking.status.tone())

        // Get help, at the top and on the journey the passenger is actually
        // taking. Not at the foot of a scroll: the moment it is needed is the
        // moment nobody scrolls. Shown only while the ride is still live --
        // an emergency control on a receipt from last month is noise, and
        // noise is what makes a real one get ignored.
        if (booking.isActive) {
            Spacer(Modifier.height(Spacing.sm))
            var helpOpen by remember { mutableStateOf(false) }
            SecondaryAction(
                label = strings["safety.title"],
                onClick = { helpOpen = true },
                modifier = Modifier.fillMaxWidth(),
            )
            if (helpOpen) {
                HelpSheet(
                    ride = RideFacts(
                        bookingNumber = booking.number,
                        driverName = booking.driverName,
                        plate = booking.vehiclePlate,
                        origin = booking.pickupStationName,
                        destination = booking.dropoffDestinationName,
                    ),
                    tripId = booking.tripId,
                    bookingId = booking.id,
                    onDismiss = { helpOpen = false },
                )
            }
        }

        if (state.isStale) {
            Spacer(Modifier.height(Spacing.sm))
            // Cached data, honestly labelled, rather than a spinner over nothing.
            Text(
                strings["common.state.offline"],
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        if (state.errorCode != null) {
            InlineError(state.errorCode!!, context = state.errorContext)
        }

        Spacer(Modifier.height(Spacing.xl))

        if (state.showCode && booking.verificationCode != null) {
            BoardingCode(booking.verificationCode!!)
            Spacer(Modifier.height(Spacing.xl))
        }

        VelroCard {
            Column {
                Journey(state.originName, state.destinationName)
                booking.scheduledDepartureAt?.let {
                    Spacer(Modifier.height(Spacing.sm))
                    Text(
                        Calendars.dateTime(it, strings.locale),
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                Spacer(Modifier.height(Spacing.md))
                Receipt(booking)
            }
        }

        // Who drove, and in what. Absent until a driver is assigned, which is
        // a state to render rather than a gap to apologise for.
        if (booking.driverName != null || booking.vehiclePlate != null) {
            Spacer(Modifier.height(Spacing.lg))
            VelroCard { Vehicle(booking) }
        }

        Spacer(Modifier.height(Spacing.xl))

        if (state.canCancel) {
            SecondaryAction(
                label = strings["booking.action.cancel"],
                onClick = { onEvent(BookingDetailEvent.Cancel("PASSENGER_CANCELLED")) },
                enabled = !state.isCancelling,
            )
        }

        if (state.canRate) {
            Spacer(Modifier.height(Spacing.xl))
            RatingPrompt { score -> onEvent(BookingDetailEvent.Rate(score, null)) }
        }

        if (state.ratingSubmitted) {
            Spacer(Modifier.height(Spacing.lg))
            Text(
                strings["rating.action.submit"],
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.primary,
            )
        }
    }
}

@Composable
private fun Receipt(booking: Booking) {
    val strings = LocalVelroStrings.current
    Column {
        // The lines are shown only when they account for the total. A receipt
        // that does not add up is worse than one that only states the total.
        if (booking.breakdownExplainsTotal) {
            booking.fareBreakdown.forEach { component ->
                FareRow(
                    if (component.quantity > 1) {
                        strings[
                            "receipt.line.times",
                            "label" to strings[component.key],
                            "count" to component.quantity,
                        ]
                    } else {
                        strings[component.key]
                    },
                    component.total,
                )
            }
            HorizontalDivider(Modifier.padding(vertical = Spacing.sm))
        }
        FareRow(strings["ride.label.fare"], booking.fareTotal, bold = true)

        booking.cancellationFee?.let { fee ->
            Spacer(Modifier.height(Spacing.sm))
            FareRow(strings["receipt.label.cancellation_fee"], fee)
            // Zero is worth saying: the passenger should be told they were not
            // charged rather than left to infer it from an absent line.
            if (fee.amountMinor == 0L) {
                Text(
                    strings["receipt.label.no_fee"],
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        Spacer(Modifier.height(Spacing.sm))
        Text(
            strings["payment.method.${booking.paymentMethod.name.lowercase()}"],
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun Vehicle(booking: Booking) {
    val strings = LocalVelroStrings.current
    Column {
        Text(strings["receipt.label.driver"], style = MaterialTheme.typography.labelSmall,
             color = MaterialTheme.colorScheme.onSurfaceVariant)
        booking.driverName?.let {
            Text(it, style = MaterialTheme.typography.bodyLarge)
        }
        booking.vehiclePlate?.let { plate ->
            Spacer(Modifier.height(Spacing.sm))
            Text(strings["receipt.label.vehicle"], style = MaterialTheme.typography.labelSmall,
                 color = MaterialTheme.colorScheme.onSurfaceVariant)
            // A plate is read off a physical car: never mirrored, never in
            // Eastern digits, whatever the app language.
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                Text(plate, style = MaterialTheme.typography.bodyLarge,
                     fontWeight = FontWeight.SemiBold)
            }
            booking.vehicleDescription?.let {
                Text(it, style = MaterialTheme.typography.bodyMedium,
                     color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

@Composable
private fun Journey(origin: String?, destination: String?) {
    val strings = LocalVelroStrings.current
    Column {
        Text(
            strings["driver.label.pickup"],
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(origin ?: "—", style = MaterialTheme.typography.bodyLarge)
        Spacer(Modifier.height(Spacing.sm))
        Text(
            strings["location.label.destination"],
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(destination ?: "—", style = MaterialTheme.typography.bodyLarge)
    }
}

@Composable
private fun RatingPrompt(onRate: (Int) -> Unit) {
    val strings = LocalVelroStrings.current
    var score by remember { mutableIntStateOf(0) }

    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
        Text(strings["rating.title"], style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(Spacing.md))
        Row {
            for (star in 1..5) {
                IconButton(
                    onClick = {
                        score = star
                        onRate(star)
                    }
                ) {
                    Icon(
                        if (star <= score) Icons.Filled.Star else Icons.Filled.StarBorder,
                        // A star carries meaning, so it is labelled rather than
                        // left as decoration for a screen reader.
                        contentDescription = "$star",
                        tint = if (star <= score) MaterialTheme.colorScheme.secondary
                        else MaterialTheme.colorScheme.outline,
                    )
                }
            }
        }
    }
}
