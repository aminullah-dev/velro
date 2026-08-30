package af.velro.feature.trip

import af.velro.data.api.ApiException
import af.velro.data.api.ApiResult
import af.velro.data.repository.BookingRepository
import af.velro.data.repository.GeographyRepository
import af.velro.domain.Booking
import af.velro.domain.BookingStatus
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * One booking, tracked.
 *
 * Reads from the cache first and refreshes behind it, so a passenger who opens
 * this in a valley with no signal still sees their seat, their code and where
 * they are going -- which is the whole point of caching bookings at all.
 */
data class BookingDetailUiState(
    val booking: Booking? = null,
    val originName: String? = null,
    val destinationName: String? = null,
    val isRefreshing: Boolean = false,
    val isStale: Boolean = false,
    val isCancelling: Boolean = false,
    val ratingSubmitted: Boolean = false,
    val errorCode: String? = null,
    val errorContext: Map<String, Any?> = emptyMap(),
) {
    val canCancel: Boolean get() = booking?.canCancel == true && !isCancelling
    val canRate: Boolean get() = booking?.canRate == true && !ratingSubmitted
    val showCode: Boolean
        get() = booking?.status in setOf(
            BookingStatus.CONFIRMED, BookingStatus.DRIVER_ASSIGNED, BookingStatus.READY,
        )
}

sealed interface BookingDetailEvent {
    data object Refresh : BookingDetailEvent
    data class Cancel(val reasonCode: String) : BookingDetailEvent
    data class Rate(val score: Int, val comment: String?) : BookingDetailEvent
    data object DismissError : BookingDetailEvent
}

/** Often enough to catch a driver arriving, cheap enough for a data bundle. */
private const val POLL_SECONDS = 12L

@HiltViewModel
class BookingDetailViewModel @Inject constructor(
    private val bookings: BookingRepository,
    private val geography: GeographyRepository,
    savedState: SavedStateHandle,
) : ViewModel() {

    private val bookingId: String = checkNotNull(savedState["bookingId"])

    private val _state = MutableStateFlow(BookingDetailUiState())
    val state: StateFlow<BookingDetailUiState> = _state.asStateFlow()

    init {
        observeCache()
        refresh()
        poll()
    }

    /**
     * Keep the screen honest while she is looking at it.
     *
     * This is the screen a passenger holds open at a station, and everything on
     * it changes without her: the driver is assigned, then arriving, then
     * there; the trip can be cancelled out from under her. Loaded once in init,
     * the boarding code stayed on screen for a journey that had been called off
     * an hour earlier.
     *
     * Stops on a terminal booking. A receipt does not change, and polling one
     * is a data bundle spent on nothing.
     */
    private fun poll() {
        viewModelScope.launch {
            while (isActive) {
                delay(POLL_SECONDS * 1000)
                val booking = _state.value.booking ?: continue
                if (!booking.isActive) return@launch
                refresh()
            }
        }
    }

    fun onEvent(event: BookingDetailEvent) {
        when (event) {
            BookingDetailEvent.Refresh -> refresh()
            is BookingDetailEvent.Cancel -> cancel(event.reasonCode)
            is BookingDetailEvent.Rate -> rate(event.score, event.comment)
            BookingDetailEvent.DismissError -> _state.update { it.copy(errorCode = null) }
        }
    }

    private fun observeCache() {
        viewModelScope.launch {
            bookings.booking(bookingId).collect { cached ->
                if (cached == null) return@collect
                // The name recorded with the booking wins: the cache may be
                // empty on a handset that has never opened the booking flow,
                // and a station renamed since would otherwise relabel an old
                // receipt with a journey the passenger never took.
                val origin = cached.pickupStationName
                    ?: geography.station(cached.pickupStationId)?.name
                val destination = cached.dropoffDestinationName
                    ?: geography.destination(cached.dropoffDestinationId)?.name
                _state.update {
                    it.copy(
                        booking = cached,
                        originName = origin,
                        destinationName = destination,
                    )
                }
            }
        }
    }

    private fun refresh() {
        _state.update { it.copy(isRefreshing = true, errorCode = null) }
        viewModelScope.launch {
            when (val result = bookings.refreshBooking(bookingId)) {
                is ApiResult.Success ->
                    _state.update { it.copy(isRefreshing = false, isStale = false) }
                is ApiResult.Failure -> _state.update {
                    if (it.booking != null && result.error.code == ApiException.OFFLINE) {
                        // Cached data plus an honest marker beats an error page
                        // over information that is still perfectly usable.
                        it.copy(isRefreshing = false, isStale = true)
                    } else {
                        it.failed(result.error)
                    }
                }
            }
        }
    }

    private fun cancel(reasonCode: String) {
        _state.update { it.copy(isCancelling = true, errorCode = null) }
        viewModelScope.launch {
            when (val result = bookings.cancel(bookingId, reasonCode)) {
                is ApiResult.Success -> _state.update { it.copy(isCancelling = false) }
                is ApiResult.Failure ->
                    _state.update { it.copy(isCancelling = false).failed(result.error) }
            }
        }
    }

    private fun rate(score: Int, comment: String?) {
        val tripId = _state.value.booking?.tripId ?: return
        viewModelScope.launch {
            when (
                val result = bookings.rate(tripId, score, comment, bookingId)
            ) {
                is ApiResult.Success -> _state.update { it.copy(ratingSubmitted = true) }
                is ApiResult.Failure -> _state.update {
                    // Already rated is not a failure worth alarming anyone over.
                    if (result.error.code == "RATING_ALREADY_SUBMITTED") {
                        it.copy(ratingSubmitted = true)
                    } else {
                        it.failed(result.error)
                    }
                }
            }
        }
    }

    private fun BookingDetailUiState.failed(error: ApiException) = copy(
        isRefreshing = false,
        errorCode = error.code,
        errorContext = error.context,
    )
}
