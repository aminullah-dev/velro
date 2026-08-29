package af.velro.feature.driver

import af.velro.core.i18n.Calendars
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
import af.velro.domain.Earnings
import af.velro.domain.LedgerEntry
import af.velro.domain.LedgerKind
import af.velro.domain.MoneyValue
import af.velro.domain.PayoutOptions
import af.velro.domain.Settlement
import af.velro.domain.SettlementStatus
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
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun EarningsRoute(viewModel: EarningsViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    EarningsScreen(state, viewModel::onEvent)
}

@Composable
fun EarningsScreen(
    state: EarningsUiState,
    onEvent: (EarningsEvent) -> Unit,
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current

    if (state.isLoading && state.isEmpty) {
        LoadingState(modifier.fillMaxSize())
        return
    }
    // Only when the balance itself could not be read is the whole screen an
    // error. A driver who cannot see what they have earned has nothing here.
    if (state.isEmpty && state.errorCode != null) {
        ErrorState(
            errorCode = state.errorCode!!,
            context = state.errorContext,
            onRetry = { onEvent(EarningsEvent.Refresh) },
            modifier = modifier.fillMaxSize(),
        )
        return
    }

    Column(
        modifier
            .fillMaxSize()
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(Spacing.lg),
        verticalArrangement = Arrangement.spacedBy(Spacing.md),
    ) {
        Text(
            strings["driver.earnings.title"],
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.SemiBold,
        )

        state.earnings?.let { Balance(it) }

        if (state.errorCode != null) {
            InlineError(state.errorCode!!, context = state.errorContext)
        }

        state.payout?.let { Payout(it, state, onEvent) }

        Ledger(state, onEvent)

        state.payout?.history?.filter { !it.isOpen }?.takeIf { it.isNotEmpty() }?.let {
            History(it)
        }

        Spacer(Modifier.height(Spacing.xl))
    }
}

@Composable
private fun Balance(earnings: Earnings) {
    val strings = LocalVelroStrings.current
    VelroCard {
        Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
            Text(
                strings["driver.earnings.available"],
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                MoneyFormatter.format(earnings.available, strings),
                style = MaterialTheme.typography.headlineMedium,
                fontWeight = FontWeight.Bold,
            )

            // Shown only when there is one. A permanent "pending: 0" line
            // teaches a driver to stop reading the rows.
            if (earnings.pending.amountMinor > 0) {
                Spacer(Modifier.height(Spacing.xs))
                Figure("driver.earnings.pending", earnings.pending, emphasise = true)
            }

            Spacer(Modifier.height(Spacing.sm))
            HorizontalDivider()
            Spacer(Modifier.height(Spacing.sm))

            Figure("driver.earnings.lifetime_earned", earnings.lifetimeEarned)
            Figure("driver.earnings.lifetime_commission", earnings.lifetimeCommission)
            if (earnings.lifetimePaid.amountMinor > 0) {
                Figure("driver.earnings.lifetime_paid", earnings.lifetimePaid)
            }
            Row(
                Modifier.fillMaxWidth().padding(vertical = Spacing.xxs),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text(
                    strings["driver.earnings.trips"],
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(
                    Numerals.localise(earnings.completedTrips.toString(), strings.locale),
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }
}

@Composable
private fun Figure(key: String, amount: MoneyValue, emphasise: Boolean = false) {
    val strings = LocalVelroStrings.current
    Row(
        Modifier.fillMaxWidth().padding(vertical = Spacing.xxs),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            strings[key],
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(
            MoneyFormatter.format(amount, strings),
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = if (emphasise) FontWeight.SemiBold else FontWeight.Normal,
            color = if (emphasise) MaterialTheme.colorScheme.primary
            else MaterialTheme.colorScheme.onSurface,
        )
    }
}

@Composable
private fun Payout(
    payout: PayoutOptions,
    state: EarningsUiState,
    onEvent: (EarningsEvent) -> Unit,
) {
    val strings = LocalVelroStrings.current
    val open = payout.history.firstOrNull { it.isOpen }

    VelroCard {
        Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
            when {
                state.requestedReference != null -> Text(
                    strings[
                        "driver.earnings.open_request",
                        "reference" to state.requestedReference,
                    ],
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.primary,
                )
                // Already asked: say which request and for how much, so the
                // driver knows the money is accounted for rather than gone.
                open != null -> {
                    Text(
                        strings["driver.earnings.open_request", "reference" to open.reference],
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Text(
                        MoneyFormatter.format(open.amount, strings),
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    StatusLabel(open.status)
                }
                payout.canRequest -> PrimaryAction(
                    label = strings[
                        "driver.earnings.request_all",
                        "amount" to MoneyFormatter.format(
                            state.earnings?.available ?: payout.minimum, strings
                        ),
                    ],
                    onClick = { onEvent(EarningsEvent.RequestPayout) },
                    loading = state.isRequesting,
                    modifier = Modifier.fillMaxWidth(),
                )
                // Cannot ask yet: say how much is needed rather than showing a
                // dead button with no explanation.
                else -> Text(
                    strings[
                        "driver.earnings.minimum_note",
                        "amount" to MoneyFormatter.format(payout.minimum, strings),
                    ],
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun Ledger(state: EarningsUiState, onEvent: (EarningsEvent) -> Unit) {
    val strings = LocalVelroStrings.current

    Text(strings["driver.earnings.ledger"], style = MaterialTheme.typography.titleMedium)

    if (state.entries.isEmpty()) {
        Text(
            strings["driver.earnings.ledger_empty"],
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        return
    }

    VelroCard {
        Column {
            state.entries.forEachIndexed { index, entry ->
                if (index > 0) HorizontalDivider()
                LedgerRow(entry)
            }
        }
    }

    if (state.hasMore) {
        SecondaryAction(
            label = strings["driver.earnings.load_more"],
            onClick = { onEvent(EarningsEvent.LoadMore) },
            enabled = !state.isLoadingMore,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun LedgerRow(entry: LedgerEntry) {
    val strings = LocalVelroStrings.current
    Row(
        Modifier.fillMaxWidth().padding(vertical = Spacing.sm),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(
                strings[
                    when (entry.kind) {
                        LedgerKind.UNKNOWN -> "ledger.kind.adjustment"
                        else -> "ledger.kind.${entry.kind.name.lowercase()}"
                    }
                ],
                style = MaterialTheme.typography.bodyMedium,
            )
            Text(
                Calendars.date(entry.createdAt, strings.locale),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Column(horizontalAlignment = Alignment.End) {
            Text(
                // The sign is the point of the row, so it is never dropped: a
                // deduction that reads like a credit is a support call.
                (if (entry.isCredit) "+" else "−") +
                    MoneyFormatter.format(entry.amount.copy(
                        amountMinor = kotlin.math.abs(entry.amount.amountMinor)
                    ), strings),
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.SemiBold,
                color = if (entry.isCredit) MaterialTheme.colorScheme.primary
                else MaterialTheme.colorScheme.error,
                textAlign = TextAlign.End,
            )
            Text(
                strings[
                    "driver.earnings.balance_after",
                    "amount" to MoneyFormatter.format(entry.balanceAfter, strings),
                ],
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun History(settled: List<Settlement>) {
    val strings = LocalVelroStrings.current
    Text(strings["driver.earnings.history"], style = MaterialTheme.typography.titleMedium)
    VelroCard {
        Column {
            settled.forEachIndexed { index, s ->
                if (index > 0) HorizontalDivider()
                Row(
                    Modifier.fillMaxWidth().padding(vertical = Spacing.sm),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(
                            MoneyFormatter.format(s.amount, strings),
                            style = MaterialTheme.typography.bodyMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                        StatusLabel(s.status)
                        // A refusal without a reason is the worst version of
                        // this screen, so the reason travels with the record.
                        s.rejectionReason?.let {
                            Text(
                                it,
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.error,
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun StatusLabel(status: SettlementStatus) {
    val strings = LocalVelroStrings.current
    Text(
        strings["settlement.status.${status.name.lowercase()}"],
        style = MaterialTheme.typography.labelSmall,
        color = when (status) {
            SettlementStatus.PAID -> MaterialTheme.colorScheme.primary
            SettlementStatus.REJECTED -> MaterialTheme.colorScheme.error
            else -> MaterialTheme.colorScheme.onSurfaceVariant
        },
    )
}
