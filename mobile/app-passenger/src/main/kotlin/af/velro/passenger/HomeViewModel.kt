package af.velro.passenger

import af.velro.data.api.ApiResult
import af.velro.data.repository.BookingRepository
import af.velro.data.repository.NegotiationRepository
import af.velro.domain.Booking
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
import kotlinx.coroutines.joinAll
import kotlinx.coroutines.launch

data class HomeUiState(
    val bookings: List<Booking> = emptyList(),
    /**
     * The ask she has open right now, if any.
     *
     * Home showed only bookings, so a woman who closed the app while drivers
     * were bidding had no route back to her own request — and the server
     * refuses a second one while the first is alive. She was locked out of the
     * journey she had started, by her own app, with no way to see why.
     */
    val openRequest: RideRequest? = null,
    val isLoading: Boolean = true,
    /**
     * The last refresh did not land, so the list is the cache.
     *
     * Home had no failure state at all: three branches, loading, empty and
     * list. A passenger opening the app on a cold cache with no signal was
     * shown "No bookings yet" -- an assertion about her own journeys that the
     * app had not managed to check -- with nothing to retry.
     */
    val isStale: Boolean = false,
    /**
     * A refresh the passenger asked for, as opposed to one the app started.
     *
     * Separate from [isLoading], which covers the first load and draws over the
     * whole screen. This one only drives the pull indicator, so the list she is
     * already reading stays on screen and legible while it updates.
     */
    val isRefreshing: Boolean = false,
    val errorCode: String? = null,
    val errorContext: Map<String, Any?> = emptyMap(),
)

/** Often enough that a countdown does not visibly stall, rarely enough to be
 *  cheap on a data bundle. */
private const val POLL_SECONDS = 10L

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val bookings: BookingRepository,
    private val negotiation: NegotiationRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(HomeUiState())
    val state: StateFlow<HomeUiState> = _state.asStateFlow()

    init {
        // The cache drives the list; the refresh only updates it. A passenger
        // opening the app with no signal still sees their bookings.
        viewModelScope.launch {
            bookings.recent().collect { cached ->
                _state.update { it.copy(bookings = cached, isLoading = false) }
            }
        }
        viewModelScope.launch { refreshBookings() }
        viewModelScope.launch { refreshOpenRequest() }
        poll()
    }

    fun refresh() {
        _state.update { it.copy(errorCode = null, isRefreshing = true) }
        viewModelScope.launch {
            // Both, not whichever finishes first. These are two calls to two
            // endpoints, and clearing the flag after one of them would stop the
            // indicator while half the screen was still the old data -- which
            // reads as "refreshed, nothing changed" when nothing had.
            joinAll(
                launch { refreshBookings() },
                launch { refreshOpenRequest() },
            )
            _state.update { it.copy(isRefreshing = false) }
        }
    }

    private suspend fun refreshBookings() {
        run {
            when (val result = bookings.refreshBookings()) {
                is ApiResult.Success -> _state.update { it.copy(isStale = false) }
                is ApiResult.Failure -> _state.update { current ->
                    // With something cached, say it is old and leave it alone.
                    // With nothing, this is the only screen she has: an error
                    // she can act on beats a sentence about her journeys that
                    // was never true.
                    if (current.bookings.isNotEmpty()) current.copy(isStale = true)
                    else current.copy(
                        isStale = true,
                        isLoading = false,
                        errorCode = result.error.code,
                        errorContext = result.error.context,
                    )
                }
            }
        }
    }

    private suspend fun refreshOpenRequest() {
        // A failure leaves the card as it was rather than hiding it: the
        // request has not gone away because the network did.
        val mine = (negotiation.myRequests() as? ApiResult.Success)?.value ?: return
        _state.update { it.copy(openRequest = mine.firstOrNull { r -> r.isOpen }) }
    }

    /**
     * Keep the card honest.
     *
     * Offers arrive while she is looking at this screen and the request expires
     * on its own, so a card rendered once is wrong within a minute. Same
     * cadence the driver's board already uses.
     */
    private fun poll() {
        viewModelScope.launch {
            while (isActive) {
                delay(POLL_SECONDS * 1000)
                refreshOpenRequest()
            }
        }
    }
}
