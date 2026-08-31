package af.velro.feature.driver

import af.velro.data.api.ApiException
import af.velro.data.api.ApiResult
import af.velro.data.repository.DriverRepository
import af.velro.data.repository.WalletRepository
import af.velro.domain.Earnings
import af.velro.domain.EarningsPeriod
import af.velro.domain.EarningsSummary
import af.velro.domain.LedgerEntry
import af.velro.domain.PayoutOptions
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.async
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Earnings and the wallet, section 88.
 *
 * A driver checks this to answer one of two questions: "what have I made?" and
 * "when do I get it?". The summary answers the first, the ledger justifies it,
 * and the payout section answers the second.
 */
data class EarningsUiState(
    val earnings: Earnings? = null,
    val entries: List<LedgerEntry> = emptyList(),
    val payout: PayoutOptions? = null,
    /**
     * The chart's data, or null while it loads or if only it failed.
     *
     * Its own nullable field rather than a flag on the screen: the balance
     * must render whether or not the summary arrived. A driver checking what
     * he is owed should not lose that number because a chart endpoint was
     * slow.
     */
    val summary: EarningsSummary? = null,
    val period: EarningsPeriod = EarningsPeriod.DAY,
    val isLoading: Boolean = true,
    val isLoadingMore: Boolean = false,
    val isRequesting: Boolean = false,
    val hasMore: Boolean = false,
    val nextOffset: Int = 0,
    /** The ledger call failed. Distinct from a ledger that is genuinely empty. */
    val ledgerFailed: Boolean = false,
    val requestedReference: String? = null,
    val errorCode: String? = null,
    val errorContext: Map<String, Any?> = emptyMap(),
) {
    /** The summary is the screen; the ledger and payout box are enrichment. */
    val isEmpty: Boolean get() = earnings == null
}

sealed interface EarningsEvent {
    data object Refresh : EarningsEvent

    /** Switch the chart between days, weeks and months. */
    data class PeriodChanged(val period: EarningsPeriod) : EarningsEvent
    data object LoadMore : EarningsEvent
    data object RequestPayout : EarningsEvent
    data object DismissConfirmation : EarningsEvent
}

private const val PAGE = 20

/**
 * How many bars each period shows.
 *
 * Fourteen days rather than seven: a driver comparing this week with last
 * needs both on screen. Twelve weeks is a season; twelve months is a year.
 */
private fun bucketsFor(period: EarningsPeriod): Int = when (period) {
    EarningsPeriod.DAY -> 14
    EarningsPeriod.WEEK -> 12
    EarningsPeriod.MONTH -> 12
}

@HiltViewModel
class EarningsViewModel @Inject constructor(
    private val drivers: DriverRepository,
    private val wallet: WalletRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(EarningsUiState())
    val state: StateFlow<EarningsUiState> = _state.asStateFlow()

    init { load() }

    fun onEvent(event: EarningsEvent) {
        when (event) {
            EarningsEvent.Refresh -> load()
            EarningsEvent.LoadMore -> loadMore()
            EarningsEvent.RequestPayout -> requestPayout()
            is EarningsEvent.PeriodChanged ->
                if (event.period != _state.value.period) loadSummary(event.period)
            EarningsEvent.DismissConfirmation ->
                _state.update { it.copy(requestedReference = null) }
        }
    }

    private fun load() {
        _state.update { it.copy(isLoading = true, errorCode = null) }
        viewModelScope.launch {
            // Three independent reads, so they go out together: on a weak
            // connection running them in series is three round trips of waiting
            // for a screen that shows one thing.
            val summaryJob = async { drivers.earnings() }
            val ledgerJob = async { wallet.ledger(limit = PAGE, offset = 0) }
            val payoutJob = async { wallet.payoutOptions() }
            val chartJob = async {
                wallet.earningsSummary(_state.value.period, bucketsFor(_state.value.period))
            }

            when (val summary = summaryJob.await()) {
                is ApiResult.Success -> {
                    val ledger = ledgerJob.await()
                    val payout = payoutJob.await()
                    val chart = chartJob.await()
                    _state.update {
                        it.copy(
                            earnings = summary.value,
                            // The balance is the load-bearing number. If only
                            // the ledger failed, show the balance and an empty
                            // list rather than an error over the whole screen.
                            entries = (ledger as? ApiResult.Success)?.value?.entries.orEmpty(),
                            // "I could not read it" is not "there is nothing".
                            //
                            // The ledger failure was folded into an empty list
                            // and the screen printed "Nothing yet. Your first
                            // trip will show here" -- a money screen asserting
                            // an empty history it never actually read, to a
                            // driver who has been working all week.
                            ledgerFailed = ledger !is ApiResult.Success,
                            hasMore = (ledger as? ApiResult.Success)?.value?.hasMore ?: false,
                            nextOffset = (ledger as? ApiResult.Success)?.value?.nextOffset ?: 0,
                            payout = (payout as? ApiResult.Success)?.value,
                            summary = (chart as? ApiResult.Success)?.value,
                            isLoading = false,
                            errorCode = null,
                        )
                    }
                }
                is ApiResult.Failure -> _state.update { it.withError(summary.error) }
            }
        }
    }

    private fun loadMore() {
        val current = _state.value
        if (current.isLoadingMore || !current.hasMore) return
        _state.update { it.copy(isLoadingMore = true) }
        viewModelScope.launch {
            when (val page = wallet.ledger(limit = PAGE, offset = current.nextOffset)) {
                is ApiResult.Success -> _state.update {
                    // Guard against a duplicate arriving from a page boundary:
                    // a repeated entry in a money list reads as money counted
                    // twice, which is worse than a missing row.
                    val seen = it.entries.mapTo(mutableSetOf()) { e -> e.id }
                    it.copy(
                        entries = it.entries + page.value.entries.filter { e -> e.id !in seen },
                        hasMore = page.value.hasMore,
                        nextOffset = page.value.nextOffset,
                        isLoadingMore = false,
                    )
                }
                is ApiResult.Failure ->
                    _state.update { it.copy(isLoadingMore = false).withError(page.error) }
            }
        }
    }

    /**
     * Re-fetch only the chart.
     *
     * The period tab changes one card. Reloading the balance, the ledger and
     * the payout box with it would blank most of the screen to redraw a row
     * of bars, on a connection where each of those is a round trip.
     */
    private fun loadSummary(period: EarningsPeriod) {
        // Applied immediately so the selected tab responds to the tap rather
        // than to the network.
        _state.update { it.copy(period = period) }
        viewModelScope.launch {
            when (val result = wallet.earningsSummary(period, bucketsFor(period))) {
                is ApiResult.Success -> _state.update {
                    // Guard against a slow reply for a period the driver has
                    // already tabbed away from, which would draw last week's
                    // bars under a "monthly" heading.
                    if (it.period != period) it else it.copy(summary = result.value)
                }
                // The previous chart stays. A failed switch should not empty
                // a card that was fine a second ago.
                is ApiResult.Failure -> Unit
            }
        }
    }

    private fun requestPayout() {
        if (_state.value.payout?.canRequest != true || _state.value.isRequesting) return
        _state.update { it.copy(isRequesting = true, errorCode = null) }
        viewModelScope.launch {
            when (val result = wallet.requestPayout()) {
                is ApiResult.Success -> {
                    _state.update {
                        it.copy(isRequesting = false, requestedReference = result.value.reference)
                    }
                    // Re-read: the money has moved from available to pending,
                    // and showing the old balance beside a payout confirmation
                    // is the moment a driver stops believing the numbers.
                    load()
                }
                is ApiResult.Failure ->
                    _state.update { it.copy(isRequesting = false).withError(result.error) }
            }
        }
    }
}

private fun EarningsUiState.withError(error: ApiException) = copy(
    isLoading = false,
    isRequesting = false,
    errorCode = error.code,
    errorContext = error.context,
)
