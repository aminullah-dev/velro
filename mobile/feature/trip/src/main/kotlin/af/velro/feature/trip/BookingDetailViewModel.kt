package af.velro.feature.trip

import af.velro.data.sync.SyncQueue
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
    /** A cancel or rating saved for the connection's return, not yet applied. */
    val queuedOffline: Boolean = false,
    val isStale: Boolean = false,
    /** The road, drawn, when the server can draw it. */
    val journeyMap: af.velro.data.repository.TripMapData? = null,
    /** Where the car is right now, while a car is owed to this booking. */
    val vehicle: af.velro.data.repository.MapPlace? = null,
    val vehicleAgeSeconds: Int? = null,
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
    private val queue: SyncQueue,
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
                refresh(clearError = false)
                refreshVehicle(booking)
            }
        }
    }

    /**
     * The car's dot. Only asked for while a car is actually owed -- assigned
     * and not yet finished -- and every empty or failed answer simply clears
     * the dot. The server enforces the same rule; asking outside it would
     * just be told null.
     */
    private suspend fun refreshVehicle(booking: Booking) {
        if (booking.status !in TRACKABLE) {
            if (_state.value.vehicle != null) {
                _state.update { it.copy(vehicle = null, vehicleAgeSeconds = null) }
            }
            return
        }
        loadJourneyMap(booking)
        val answer = bookings.vehicleLocation(booking.id)
        val ping = (answer as? ApiResult.Success)?.value
        _state.update {
            it.copy(
                vehicle = ping?.let { p ->
                    af.velro.data.repository.MapPlace("", p.latitude, p.longitude)
                },
                vehicleAgeSeconds = ping?.ageSeconds,
            )
        }
    }

    /** Once per booking: the same preview the booking flow showed. */
    private suspend fun loadJourneyMap(booking: Booking) {
        if (_state.value.journeyMap != null) return
        (geography.journeyMap(
            booking.pickupStationId, booking.dropoffDestinationId,
        ) as? ApiResult.Success)?.let { drawn ->
            _state.update { it.copy(journeyMap = drawn.value) }
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

    /**
     * @param clearError only when the person asked for this.
     *
     * The twelve-second poll calls straight through here, and clearing the
     * error unconditionally meant a failed cancellation's message survived
     * about as long as it took to read half of it. A passenger who tapped
     * "cancel my seat", saw a red line flash and then a screen that looked
     * exactly as before could not tell whether her seat was cancelled or not
     * -- on a booking she may be about to stop waiting for.
     */
    private fun refresh(clearError: Boolean = true) {
        _state.update {
            it.copy(isRefreshing = true, errorCode = if (clearError) null else it.errorCode)
        }
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
                    if (result.error.code == ApiException.OFFLINE) {
                        // A cancel spoken in a dead valley used to be simply
                        // lost -- the seat stayed held and the passenger was a
                        // no-show on a trip she had renounced. Queued now; the
                        // status on screen stays honest (still booked) until
                        // the server confirms.
                        queue.enqueueCancel(bookingId, reasonCode)
                        _state.update {
                            it.copy(isCancelling = false, queuedOffline = true)
                        }
                    } else {
                        _state.update { it.copy(isCancelling = false).failed(result.error) }
                    }
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
                is ApiResult.Failure -> if (
                    result.error.code == ApiException.OFFLINE
                ) {
                    queue.enqueueRating(tripId, score, comment, bookingId)
                    _state.update {
                        it.copy(ratingSubmitted = true, queuedOffline = true)
                    }
                } else {
                    _state.update {
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
    }

    private fun BookingDetailUiState.failed(error: ApiException) = copy(
        isRefreshing = false,
        errorCode = error.code,
        errorContext = error.context,
    )
}

/** A car is owed: assigned, ready to board, or aboard. */
private val TRACKABLE = setOf(
    BookingStatus.DRIVER_ASSIGNED, BookingStatus.READY, BookingStatus.ONBOARD,
)
