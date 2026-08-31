package af.velro.feature.driver

import androidx.compose.material3.FilterChip
import af.velro.domain.EarningsSummary
import af.velro.domain.EarningsPeriod
import af.velro.domain.EarningsBucket
import af.velro.core.ui.component.EarningsChart
import af.velro.core.i18n.Calendars
import af.velro.core.i18n.MoneyFormatter
import af.velro.core.i18n.Numerals
import af.velro.core.ui.component.ErrorState
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.component.VelroScreen
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import af.velro.domain.Earnings
import af.velro.domain.LedgerEntry
import af.velro.domain.LedgerKind
import af.velro.domain.MoneyValue
import af.velro.domain.PayoutOptions
import af.velro.domain.Settlement
import af.velro.domain.SettlementStatus
import androidx.compose.foundation.clickable
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
import androidx.compose.material.icons.filled.ArrowDownward
import androidx.compose.material.icons.filled.ArrowUpward
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
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
fun EarningsRoute(
    onBack: () -> Unit = {},
    viewModel: EarningsViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    EarningsScreen(state, viewModel::onEvent, onBack = onBack)
}

@Composable
fun EarningsScreen(
    state: EarningsUiState,
    onEvent: (EarningsEvent) -> Unit,
    onBack: () -> Unit = {},
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

    VelroScreen(
        title = strings["driver.earnings.title"],
        onBack = onBack,
        modifier = modifier,
    ) {
        // The title lives in the app bar now, not twice on the screen.
        //
        // Sections are spaced like the home screen's: a step under the bar and
        // a step between cards. Emitted flush against each other, the driver's
        // money screen was the only one in the product where a card began
        // exactly where the one above it ended.
        Spacer(Modifier.height(Spacing.md))

        state.earnings?.let { Balance(it, state.payout) }

        state.summary?.let {
            Spacer(Modifier.height(Spacing.lg))
            EarningsTrend(it, state.period, onEvent)
        }

        if (state.errorCode != null) {
            Spacer(Modifier.height(Spacing.lg))
            InlineError(state.errorCode!!, context = state.errorContext)
        }

        state.payout?.let {
            Spacer(Modifier.height(Spacing.lg))
            Payout(it, state, onEvent)
        }

        Spacer(Modifier.height(Spacing.lg))
        Ledger(state, onEvent)

        state.payout?.history?.filter { !it.isOpen }?.takeIf { it.isNotEmpty() }?.let {
            Spacer(Modifier.height(Spacing.lg))
            History(it)
        }

        Spacer(Modifier.height(Spacing.xl))
    }
}

@Composable
private fun Balance(earnings: Earnings, payout: PayoutOptions?) {
    val strings = LocalVelroStrings.current
    // Fares are handed over in cash at the vehicle, so most of the time the
    // driver is holding VELRO's share rather than waiting to be paid. Which of
    // the two it is must be readable at a glance by someone who does not read
    // easily -- so it is carried by the wording, an icon and the colour, never
    // by the colour alone.
    // The same rule the home card asks, from the same place.
    //
    // This read the server's payout flag while home read `available` directly,
    // so the two screens could and did disagree. Both go through
    // Earnings.owesPlatform now, which nets `pending` in -- see EarningsTest.
    val owes = earnings.owesPlatform
    val headline = earnings.headlineAmount

    VelroCard {
        Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    strings[
                        if (owes) "driver.earnings.owed" else "driver.earnings.available"
                    ],
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Icon(
                    // Direction of travel: money leaving the driver's hands, or
                    // arriving in them.
                    imageVector = if (owes) Icons.Filled.ArrowUpward
                    else Icons.Filled.ArrowDownward,
                    contentDescription = null,   // the label beside it already says this
                    tint = if (owes) MaterialTheme.colorScheme.error
                    else MaterialTheme.colorScheme.primary,
                )
            }
            Text(
                MoneyFormatter.format(headline, strings),
                // The same size and colour the home card gives this figure.
                // Tapping "earnings" from home used to make the number the
                // driver came to check smaller and duller than the summary he
                // tapped to get here.
                style = MaterialTheme.typography.displaySmall,
                fontWeight = FontWeight.Bold,
                color = if (owes) MaterialTheme.colorScheme.error
                else MaterialTheme.colorScheme.primary,
            )
            if (owes) {
                // The number alone invites the wrong conclusion -- a driver who
                // has just been paid in cash all day does not expect to owe
                // anything. Say why, in one sentence.
                Text(
                    strings["driver.earnings.owed_explained"],
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            // Shown only when there is one. A permanent "pending: 0" line
            // teaches a driver to stop reading the rows.
            if (earnings.pending.amountMinor != 0L) {
                Spacer(Modifier.height(Spacing.xs))
                Figure(
                    // The direction of the pending amount is the sign of the
                    // pending amount, not the sign of the available balance.
                    //
                    // `owes` is derived from `available`, and requesting a
                    // settlement moves the debt out of `available` into
                    // `pending` -- so the instant a collection is opened,
                    // `available` returns to zero, `owes` turns false, and the
                    // seven afghani the driver is holding for VELRO was
                    // labelled "payout in progress": money on its way to him.
                    // It is the same seven, moving the other way.
                    if (earnings.pending.amountMinor < 0L)
                        "driver.earnings.pending_collection"
                    else "driver.earnings.pending",
                    MoneyValue(
                        kotlin.math.abs(earnings.pending.amountMinor),
                        earnings.pending.currency,
                    ),
                    emphasise = true,
                )
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
                // Owing is not a smaller version of being owed: there is
                // nothing to request, and the useful thing is where to pay.
                payout.owesPlatform -> {
                    Text(
                        strings["driver.earnings.settle_at_station"],
                        style = MaterialTheme.typography.bodyMedium,
                    )
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
            // Two different sentences, because they are two different facts.
            if (state.ledgerFailed) strings["driver.earnings.ledger_failed"]
            else strings["driver.earnings.ledger_empty"],
            style = MaterialTheme.typography.bodyMedium,
            color =
                if (state.ledgerFailed) MaterialTheme.colorScheme.error
                else MaterialTheme.colorScheme.onSurfaceVariant,
            modifier =
                if (state.ledgerFailed) Modifier.clickable { onEvent(EarningsEvent.Refresh) }
                else Modifier,
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
                //
                // Through MoneyFormatter.signed rather than a "+"/"−" glued on
                // here: a sign concatenated onto an already-formatted string
                // sits outside any isolate, and the bidi algorithm then moves
                // it to the far side of the digits. That is exactly what this
                // row was doing.
                MoneyFormatter.signed(
                    MoneyFormatter.format(
                        entry.amount.copy(
                            amountMinor = kotlin.math.abs(entry.amount.amountMinor)
                        ),
                        strings,
                    ),
                    negative = !entry.isCredit,
                    showPlus = entry.isCredit,
                ),
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

/**
 * How the week went, as opposed to what is owed right now.
 *
 * The balance card above answers "what do I have"; every figure on it is a
 * lifetime total or a current state. Neither tells a driver whether today was
 * worth the fuel, which is the question that decides whether he drives
 * tomorrow.
 */
@Composable
private fun EarningsTrend(
    summary: EarningsSummary,
    period: EarningsPeriod,
    onEvent: (EarningsEvent) -> Unit,
) {
    val strings = LocalVelroStrings.current
    VelroCard {
        Column {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
            ) {
                for (option in EarningsPeriod.entries) {
                    FilterChip(
                        selected = option == period,
                        onClick = { onEvent(EarningsEvent.PeriodChanged(option)) },
                        label = { Text(strings[option.labelKey()]) },
                    )
                }
            }

            Spacer(Modifier.height(Spacing.lg))

            Text(
                MoneyFormatter.format(MoneyValue(summary.totalNetMinor), strings),
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.SemiBold,
            )
            Text(
                // Trips only. `chart_summary` carries the money as well
                // because it is what the screen reader announces for the
                // whole chart; printing it here too put the same figure on
                // two consecutive lines.
                strings[
                    "driver.earnings.period_trips",
                    "trips" to Numerals.localise(
                        summary.totalTrips.toString(), strings.locale,
                    ),
                ],
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(Modifier.height(Spacing.lg))

            EarningsChart(summary = summary, labelFor = { bucket ->
                Numerals.localise(bucket.axisLabel(period), strings.locale)
            })
        }
    }
}

private fun EarningsPeriod.labelKey(): String = when (this) {
    EarningsPeriod.DAY -> "driver.earnings.period.day"
    EarningsPeriod.WEEK -> "driver.earnings.period.week"
    EarningsPeriod.MONTH -> "driver.earnings.period.month"
}

/**
 * The tick under one bar.
 *
 * Deliberately terse -- fourteen bars share the screen width, so this is the
 * day of the month, not a date. The chart's own description carries the
 * totals for anyone who needs them read out.
 */
private fun EarningsBucket.axisLabel(period: EarningsPeriod): String {
    val parts = startsOn.split("-")
    if (parts.size != 3) return startsOn
    return when (period) {
        EarningsPeriod.DAY, EarningsPeriod.WEEK -> parts[2].trimStart('0').ifEmpty { "1" }
        EarningsPeriod.MONTH -> parts[1].trimStart('0').ifEmpty { "1" }
    }
}
