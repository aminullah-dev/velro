package af.velro.feature.trip

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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.StarBorder
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun BookingDetailRoute(viewModel: BookingDetailViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    BookingDetailScreen(state, viewModel::onEvent)
}

@Composable
fun BookingDetailScreen(
    state: BookingDetailUiState,
    onEvent: (BookingDetailEvent) -> Unit,
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

    Column(
        modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = Spacing.gutter, vertical = Spacing.lg)
    ) {
        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(booking.number, style = MaterialTheme.typography.titleMedium)
            StatusChip(booking.status.messageKey(), booking.status.tone())
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
                Spacer(Modifier.height(Spacing.md))
                FareRow(strings["ride.label.fare"], booking.fareTotal, bold = true)
            }
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
