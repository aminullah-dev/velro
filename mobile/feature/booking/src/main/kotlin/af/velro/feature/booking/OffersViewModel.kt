package af.velro.feature.booking

import af.velro.data.repository.DocumentRepository
import af.velro.data.api.ApiException
import af.velro.data.api.ApiResult
import af.velro.data.api.IdempotencyKeys
import af.velro.data.repository.NegotiationRepository
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
 * Waiting for drivers to name their price, section 89.
 *
 * The passenger is standing somewhere with a phone, so this polls rather than
 * asking them to pull down: nobody refreshes a screen they are waiting on.
 */
data class OffersUiState(
    val request: RideRequest? = null,
    val isLoading: Boolean = true,
    val acceptingOfferId: String? = null,
    val accepted: NegotiationRepository.AcceptedRide? = null,
    val isCancelling: Boolean = false,
    val cancelled: Boolean = false,
    val errorCode: String? = null,
    /**
     * Each bidding driver's face, by driver id.
     *
     * Fetched after the offers and never awaited by them: a picture is what
     * makes the choice easier, and a slow one must not delay the prices that
     * make the choice possible. An absent entry draws a silhouette.
     *
     * The server refuses a driver the passenger has no live connection to, so
     * a missing entry can also mean "not allowed" -- which looks the same on
     * screen, and should.
     */
    val driverPhotos: Map<String, ByteArray> = emptyMap(),
    val errorContext: Map<String, Any?> = emptyMap(),
    /**
     * Held for the whole visit to this screen, so a retry of the same Accept
     * after a dropped connection carries the same idempotency key and gets
     * the same journey back -- never a second one. The same contract the ask
     * and the booking have carried from the start.
     */
    val attemptId: String = IdempotencyKeys.newAttemptId(),
)

sealed interface OffersEvent {
    data object Refresh : OffersEvent
    data class Accept(val offerId: String) : OffersEvent
    data object Cancel : OffersEvent
    data object DismissError : OffersEvent
}

/** Often enough to feel live, rarely enough not to drain a phone or a data bundle. */
private const val POLL_SECONDS = 6L

@HiltViewModel
class OffersViewModel @Inject constructor(
    private val negotiation: NegotiationRepository,
    private val documents: DocumentRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(OffersUiState())
    val state: StateFlow<OffersUiState> = _state.asStateFlow()

    init {
        load(showSpinner = true)
        poll()
    }

    fun onEvent(event: OffersEvent) {
        when (event) {
            OffersEvent.Refresh -> load(showSpinner = true)
            is OffersEvent.Accept -> accept(event.offerId)
            OffersEvent.Cancel -> cancel()
            OffersEvent.DismissError -> _state.update { it.copy(errorCode = null) }
        }
    }

    /**
     * The face behind each price.
     *
     * One request per driver, launched and not awaited, so the offers are on
     * screen while the pictures arrive. Only drivers not already held, because
     * this list polls every few seconds and re-fetching a face the passenger
     * is already looking at spends her data for nothing.
     *
     * A refusal is indistinguishable from an absence here, deliberately: the
     * server answers 404 both when there is no photograph and when this
     * passenger has no business seeing one, and neither is worth a message.
     */
    private fun loadPhotos(request: RideRequest?) {
        val offers = request?.liveOffers.orEmpty()
        for (offer in offers) {
            if (offer.driverId in _state.value.driverPhotos) continue
            viewModelScope.launch {
                documents.driverPhoto(offer.driverId)?.let { bytes ->
                    _state.update { it.copy(driverPhotos = it.driverPhotos + (offer.driverId to bytes)) }
                }
            }
        }
    }

    private fun poll() {
        viewModelScope.launch {
            while (isActive) {
                delay(POLL_SECONDS * 1000)
                val current = _state.value
                // Stop the moment there is nothing left to wait for: a settled
                // request polled for ever is a battery cost with no answer
                // coming.
                if (current.accepted != null || current.cancelled) return@launch
                if (current.request?.isOpen == false) return@launch
                if (current.acceptingOfferId != null) continue
                load(showSpinner = false)
            }
        }
    }

    private fun load(showSpinner: Boolean) {
        if (showSpinner) _state.update { it.copy(isLoading = true, errorCode = null) }
        viewModelScope.launch {
            when (val result = negotiation.myRequests()) {
                is ApiResult.Success -> {
                    loadPhotos(result.value.firstOrNull())
                    _state.update {
                    it.copy(
                        // The newest request is the one being waited on.
                        request = result.value.firstOrNull(),
                        isLoading = false,
                        // Cleared only when the reload was asked for, never by
                        // a background one.
                        //
                        // accept()'s failure sets the error and then reloads so
                        // the list matches what just happened -- and this line
                        // wiped the message a few hundred milliseconds later.
                        // "Somebody already took that price" appeared and
                        // vanished, so a passenger whose tap had failed saw a
                        // tap that did nothing, and pressed the same driver
                        // again.
                        errorCode = if (showSpinner) null else it.errorCode,
                    )
                    }
                }
                is ApiResult.Failure -> _state.update {
                    // A failed poll on a screen that already has offers is not
                    // worth an error banner over them.
                    if (!showSpinner && it.request != null) it
                    else it.copy(isLoading = false).withError(result.error)
                }
            }
        }
    }

    private fun accept(offerId: String) {
        if (_state.value.acceptingOfferId != null) return
        _state.update { it.copy(acceptingOfferId = offerId, errorCode = null) }
        viewModelScope.launch {
            when (val result = negotiation.accept(offerId, _state.value.attemptId)) {
                is ApiResult.Success ->
                    _state.update { it.copy(acceptingOfferId = null, accepted = result.value) }
                is ApiResult.Failure -> {
                    _state.update { it.copy(acceptingOfferId = null).withError(result.error) }
                    // Someone else may have taken it, or the driver withdrawn:
                    // re-read so the list matches what just happened.
                    load(showSpinner = false)
                }
            }
        }
    }

    private fun cancel() {
        val request = _state.value.request ?: return
        _state.update { it.copy(isCancelling = true, errorCode = null) }
        viewModelScope.launch {
            when (val result = negotiation.cancel(request.id)) {
                is ApiResult.Success ->
                    _state.update { it.copy(isCancelling = false, cancelled = true) }
                is ApiResult.Failure ->
                    _state.update { it.copy(isCancelling = false).withError(result.error) }
            }
        }
    }
}

private fun OffersUiState.withError(error: ApiException) = copy(
    isLoading = false,
    errorCode = error.code,
    errorContext = error.context,
)
