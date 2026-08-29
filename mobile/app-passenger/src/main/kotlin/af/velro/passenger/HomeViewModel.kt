package af.velro.passenger

import af.velro.data.repository.BookingRepository
import af.velro.domain.Booking
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class HomeUiState(
    val bookings: List<Booking> = emptyList(),
    val isLoading: Boolean = true,
)

@HiltViewModel
class HomeViewModel @Inject constructor(
    private val bookings: BookingRepository,
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
    }
}
