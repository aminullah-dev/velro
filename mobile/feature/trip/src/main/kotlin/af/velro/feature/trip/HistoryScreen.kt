package af.velro.feature.trip

import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import af.velro.core.i18n.Calendars
import af.velro.core.ui.component.BookingCard
import af.velro.core.ui.component.EmptyState
import af.velro.core.ui.component.ErrorState
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.component.VelroScreen
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun HistoryRoute(
    onBack: () -> Unit = {},
    onOpenBooking: (String) -> Unit,
    onBook: () -> Unit,
    viewModel: HistoryViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    HistoryScreen(state, viewModel::onEvent, onOpenBooking, onBook, onBack = onBack)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HistoryScreen(
    state: HistoryUiState,
    onEvent: (HistoryEvent) -> Unit,
    onOpenBooking: (String) -> Unit,
    onBook: () -> Unit,
    modifier: Modifier = Modifier,
    onBack: () -> Unit = {},
) {
    val strings = LocalVelroStrings.current

    // This screen owns a LazyColumn, so the frame does not scroll for it.
    VelroScreen(
        title = strings["history.title"],
        onBack = onBack,
        scrollable = false,
        modifier = modifier,
    ) {
        Row(
            Modifier.fillMaxWidth().padding(vertical = Spacing.md),
            horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
        ) {
            HistoryScope.entries.forEach { scope ->
                FilterChip(
                    selected = state.scope == scope,
                    onClick = { onEvent(HistoryEvent.ScopeChanged(scope)) },
                    label = { Text(strings["history.scope.${scope.name.lowercase()}"]) },
                )
            }
        }

        if (state.isStale) {
            // Cached rows, honestly labelled. A passenger checking an old
            // receipt underground should see it, not a spinner.
            Text(
                strings["common.state.offline"],
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(bottom = Spacing.sm),
            )
        }

        // Same gap home had: a Refresh event existed and only the
        // error state could send it.
        PullToRefreshBox(
            isRefreshing = state.isRefreshing,
            onRefresh = { onEvent(HistoryEvent.Refresh) },
            modifier = Modifier.fillMaxSize(),
        ) {

        when {
            state.isLoading -> LoadingState()
            state.errorCode != null && state.bookings.isEmpty() -> ErrorState(
                errorCode = state.errorCode!!,
                context = state.errorContext,
                onRetry = { onEvent(HistoryEvent.Refresh) },
            )
            state.bookings.isEmpty() -> EmptyState(
                // The two tabs are empty for different reasons, and "book one"
                // is only useful advice under the first.
                messageKey = if (state.scope == HistoryScope.UPCOMING) "empty.bookings"
                else "history.empty.past",
                actionKey = if (state.scope == HistoryScope.UPCOMING) "home.action.search" else null,
                onAction = if (state.scope == HistoryScope.UPCOMING) onBook else null,
            )
            else -> LazyColumn(
                verticalArrangement = Arrangement.spacedBy(Spacing.sm),
                contentPadding = androidx.compose.foundation.layout.PaddingValues(
                    bottom = Spacing.xl
                ),
            ) {
                items(state.bookings, key = { it.id }) { booking ->
                    Column {
                        booking.scheduledDepartureAt?.let {
                            Text(
                                Calendars.dateTime(it, strings.locale),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                                modifier = Modifier.padding(bottom = Spacing.xxs),
                            )
                        }
                        BookingCard(
                            booking = booking,
                            onClick = { onOpenBooking(booking.id) },
                        )
                    }
                }
                if (state.hasMore) {
                    item {
                        SecondaryAction(
                            label = strings["history.action.load_more"],
                            onClick = { onEvent(HistoryEvent.LoadMore) },
                            enabled = !state.isLoadingMore,
                            modifier = Modifier.padding(top = Spacing.sm),
                        )
                    }
                }
            }
        }
        }
    }
}
