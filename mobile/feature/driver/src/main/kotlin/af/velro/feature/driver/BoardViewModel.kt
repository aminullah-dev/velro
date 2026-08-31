package af.velro.feature.driver

import af.velro.data.api.ApiException
import af.velro.data.api.ApiResult
import af.velro.data.repository.NegotiationRepository
import af.velro.domain.FareOffer
import af.velro.domain.RideRequest
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Passengers waiting, and what each is offering to pay, section 89.
 *
 * The driver's side of the same conversation. Offering exactly what was asked
 * is agreeing to it -- there is no separate accept, so the driver has one thing
 * to decide rather than two.
 */
data class BoardUiState(
    val requests: List<RideRequest> = emptyList(),
    val myOffers: List<FareOffer> = emptyList(),
    val isLoading: Boolean = true,
    /**
     * A refresh the driver pulled for.
     *
     * Separate from [isLoading]: that one blanks the board behind a spinner,
     * which is right on first open and wrong when a driver is reading the
     * list and wants to know it is current.
     */
    val isRefreshing: Boolean = false,
    val offeringOn: String? = null,
    val busyRequestId: String? = null,
    val errorCode: String? = null,
    val errorContext: Map<String, Any?> = emptyMap(),
) {
    fun myOfferOn(requestId: String): FareOffer? =
        myOffers.firstOrNull { it.rideRequestId == requestId && it.isOpen }
}

sealed interface BoardEvent {
    data object Refresh : BoardEvent

    /**
     * The same fetch, keeping the list on screen.
     *
     * Its own event rather than a flag on [Refresh] so the screen cannot
     * accidentally blank the board it is showing.
     */
    data object PullToRefresh : BoardEvent
    data class StartOffering(val requestId: String) : BoardEvent
    data object StopOffering : BoardEvent
    data class Offer(
        val requestId: String,
        val amountMinor: Long,
        /** Required exactly when the request asked for a return. */
        val returnAmountMinor: Long?,
        val note: String?,
    ) : BoardEvent
    data class Withdraw(val offerId: String) : BoardEvent
    data object DismissError : BoardEvent
}

private const val POLL_SECONDS = 8L

@HiltViewModel
class BoardViewModel @Inject constructor(
    private val negotiation: NegotiationRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(BoardUiState())
    val state: StateFlow<BoardUiState> = _state.asStateFlow()

    init {
        load(showSpinner = true)
        poll()
    }

    fun onEvent(event: BoardEvent) {
        when (event) {
            // The error state still wants the full spinner -- there is nothing
            // on screen to keep. A pull has a list to preserve.
            BoardEvent.Refresh -> load(showSpinner = true)
            BoardEvent.PullToRefresh -> load(showSpinner = false, pulled = true)
            is BoardEvent.StartOffering -> _state.update { it.copy(offeringOn = event.requestId) }
            BoardEvent.StopOffering -> _state.update { it.copy(offeringOn = null) }
            is BoardEvent.Offer ->
                offer(event.requestId, event.amountMinor, event.returnAmountMinor, event.note)
            is BoardEvent.Withdraw -> withdraw(event.offerId)
            BoardEvent.DismissError -> _state.update { it.copy(errorCode = null) }
        }
    }

    private fun poll() {
        viewModelScope.launch {
            while (isActive) {
                delay(POLL_SECONDS * 1000)
                // Never while a sheet is open: a list reordering under someone
                // typing a price is how the wrong request gets a number.
                if (_state.value.offeringOn == null && _state.value.busyRequestId == null) {
                    load(showSpinner = false)
                }
            }
        }
    }

    private fun load(showSpinner: Boolean, pulled: Boolean = false) {
        if (showSpinner) _state.update { it.copy(isLoading = true, errorCode = null) }
        if (pulled) _state.update { it.copy(isRefreshing = true, errorCode = null) }
        viewModelScope.launch {
            val board = negotiation.openRequests()
            val mine = negotiation.myOffers()
            when (board) {
                is ApiResult.Success -> _state.update {
                    it.copy(
                        requests = board.value,
                        myOffers = (mine as? ApiResult.Success)?.value ?: it.myOffers,
                        isLoading = false,
                        errorCode = null,
                    )
                }
                is ApiResult.Failure -> _state.update {
                    if (!showSpinner && it.requests.isNotEmpty()) it
                    else it.copy(isLoading = false).withError(board.error)
                }
            }
            // Cleared on both paths. A driver in a valley with no signal must
            // not be left with an indicator that never stops.
            if (pulled) _state.update { it.copy(isRefreshing = false) }
        }
    }

    private fun offer(
        requestId: String,
        amountMinor: Long,
        returnAmountMinor: Long?,
        note: String?,
    ) {
        _state.update { it.copy(busyRequestId = requestId, errorCode = null) }
        viewModelScope.launch {
            when (
                val result =
                    negotiation.offer(requestId, amountMinor, returnAmountMinor, note)
            ) {
                is ApiResult.Success -> {
                    _state.update { it.copy(busyRequestId = null, offeringOn = null) }
                    load(showSpinner = false)
                }
                is ApiResult.Failure -> _state.update {
                    // The sheet stays open on a refused price, with the reason
                    // on it: the driver's next move is to change the number.
                    it.copy(busyRequestId = null).withError(result.error)
                }
            }
        }
    }

    private fun withdraw(offerId: String) {
        _state.update { it.copy(errorCode = null) }
        viewModelScope.launch {
            when (val result = negotiation.withdraw(offerId)) {
                is ApiResult.Success -> load(showSpinner = false)
                is ApiResult.Failure -> _state.update { it.withError(result.error) }
            }
        }
    }
}

private fun BoardUiState.withError(error: ApiException) = copy(
    isLoading = false,
    errorCode = error.code,
    errorContext = error.context,
)
