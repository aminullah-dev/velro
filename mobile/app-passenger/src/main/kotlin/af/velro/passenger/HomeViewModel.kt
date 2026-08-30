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
        viewModelScope.launch { bookings.refreshBookings() }
        refreshOpenRequest()
        poll()
    }

    fun refresh() {
        viewModelScope.launch { bookings.refreshBookings() }
        refreshOpenRequest()
    }

    private fun refreshOpenRequest() {
        viewModelScope.launch {
            // A failure leaves the card as it was rather than hiding it: the
            // request has not gone away because the network did.
            val mine = (negotiation.myRequests() as? ApiResult.Success)?.value ?: return@launch
            _state.update { it.copy(openRequest = mine.firstOrNull { r -> r.isOpen }) }
        }
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
