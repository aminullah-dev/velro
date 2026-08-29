package af.velro.feature.booking

import af.velro.data.api.ApiException
import af.velro.data.api.ApiResult
import af.velro.data.api.IdempotencyKeys
import af.velro.data.repository.BookingRepository
import af.velro.data.repository.GeographyRepository
import af.velro.domain.Booking
import af.velro.domain.Destination
import af.velro.domain.DestinationGroup
import af.velro.domain.District
import af.velro.domain.Station
import af.velro.domain.TripOption
import af.velro.domain.Village
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * The passenger's booking flow, section 112.
 *
 * District -> village -> station -> destination -> search -> confirm. One state
 * object for the whole flow rather than one per screen, because the steps share
 * almost all of their data and threading it through five ViewModels would
 * mostly be plumbing.
 */
data class BookingFlowUiState(
    val step: Step = Step.ORIGIN_DISTRICT,

    val districts: List<District> = emptyList(),
    val villages: List<Village> = emptyList(),
    val stations: List<Station> = emptyList(),
    val destinationGroups: List<DestinationGroup> = emptyList(),
    val options: List<TripOption> = emptyList(),

    val selectedDistrict: District? = null,
    val selectedVillage: Village? = null,
    val selectedStation: Station? = null,
    val selectedDestination: Destination? = null,
    val expandedGroupId: String? = null,
    val seatCount: Int = 1,

    val confirmedBooking: Booking? = null,

    val isLoading: Boolean = false,
    val isSubmitting: Boolean = false,
    val errorCode: String? = null,
    val errorContext: Map<String, Any?> = emptyMap(),

    /**
     * Held for the whole attempt so a retry after a dropped connection reuses
     * the same idempotency key and cannot produce a second booking.
     */
    val attemptId: String = IdempotencyKeys.newAttemptId(),
) {
    enum class Step {
        ORIGIN_DISTRICT, ORIGIN_VILLAGE, ORIGIN_STATION,
        DESTINATION, RESULTS, CONFIRMED,
    }

    val canSearch: Boolean get() = selectedStation != null && selectedDestination != null
}

sealed interface BookingEvent {
    data class DistrictChosen(val district: District) : BookingEvent
    data class VillageChosen(val village: Village) : BookingEvent
    data class StationChosen(val station: Station) : BookingEvent
    data class GroupToggled(val groupId: String) : BookingEvent
    data class DestinationChosen(val destination: Destination) : BookingEvent
    data class SeatCountChanged(val count: Int) : BookingEvent
    data class TripChosen(val option: TripOption) : BookingEvent
    data object Search : BookingEvent
    data object Back : BookingEvent
    data object Retry : BookingEvent
    data object DismissError : BookingEvent
}

sealed interface BookingEffect {
    data class Booked(val bookingId: String) : BookingEffect
}

@HiltViewModel
class BookingFlowViewModel @Inject constructor(
    private val geography: GeographyRepository,
    private val bookings: BookingRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(BookingFlowUiState())
    val state: StateFlow<BookingFlowUiState> = _state.asStateFlow()

    private val _effects = Channel<BookingEffect>(Channel.BUFFERED)
    val effects = _effects.receiveAsFlow()

    init {
        loadDistricts()
    }

    fun onEvent(event: BookingEvent) {
        when (event) {
            is BookingEvent.DistrictChosen -> chooseDistrict(event.district)
            is BookingEvent.VillageChosen -> chooseVillage(event.village)
            is BookingEvent.StationChosen -> chooseStation(event.station)
            is BookingEvent.GroupToggled -> _state.update {
                it.copy(expandedGroupId = if (it.expandedGroupId == event.groupId) null else event.groupId)
            }
            is BookingEvent.DestinationChosen -> _state.update {
                it.copy(selectedDestination = event.destination, errorCode = null)
            }
            is BookingEvent.SeatCountChanged -> _state.update {
                it.copy(seatCount = event.count.coerceIn(1, 4))
            }
            is BookingEvent.TripChosen -> book(event.option)
            BookingEvent.Search -> search()
            BookingEvent.Back -> goBack()
            BookingEvent.Retry -> retry()
            BookingEvent.DismissError -> _state.update { it.copy(errorCode = null) }
        }
    }

    private fun loadDistricts() {
        viewModelScope.launch {
            _state.update { it.copy(isLoading = true) }
            // Cache first, so the list appears immediately even with no signal.
            val cached = geography.districts().first()
            _state.update { it.copy(districts = cached, isLoading = cached.isEmpty()) }

            when (val refreshed = geography.refresh()) {
                is ApiResult.Success -> {
                    val districts = geography.districts().first()
                    _state.update {
                        it.copy(districts = districts, isLoading = false, errorCode = null)
                    }
                }
                is ApiResult.Failure -> _state.update {
                    // Only an error if there is nothing cached to show; a failed
                    // refresh over stale-but-usable data is not worth an alarm.
                    if (cached.isEmpty()) it.failed(refreshed.error)
                    else it.copy(isLoading = false)
                }
            }
        }
    }

    private fun chooseDistrict(district: District) {
        _state.update {
            it.copy(
                selectedDistrict = district,
                step = BookingFlowUiState.Step.ORIGIN_VILLAGE,
                isLoading = true,
                errorCode = null,
            )
        }
        viewModelScope.launch {
            val villages = geography.villages(district.id).first()
            _state.update { it.copy(villages = villages, isLoading = false) }
        }
    }

    private fun chooseVillage(village: Village) {
        _state.update {
            it.copy(
                selectedVillage = village,
                step = BookingFlowUiState.Step.ORIGIN_STATION,
                isLoading = true,
                errorCode = null,
            )
        }
        viewModelScope.launch {
            val stations = geography.stations(village.id).first()
            // A village with exactly one station should not ask: skip straight
            // to the destination.
            if (stations.size == 1) {
                _state.update { it.copy(stations = stations, isLoading = false) }
                chooseStation(stations.first())
            } else {
                _state.update { it.copy(stations = stations, isLoading = false) }
            }
        }
    }

    private fun chooseStation(station: Station) {
        _state.update {
            it.copy(
                selectedStation = station,
                step = BookingFlowUiState.Step.DESTINATION,
                isLoading = true,
                errorCode = null,
            )
        }
        viewModelScope.launch {
            when (val result = geography.destinationsFrom(station.id)) {
                is ApiResult.Success -> _state.update {
                    it.copy(destinationGroups = result.value, isLoading = false)
                }
                is ApiResult.Failure -> _state.update { it.failed(result.error) }
            }
        }
    }

    private fun search() {
        val current = _state.value
        val station = current.selectedStation ?: return
        val destination = current.selectedDestination ?: return

        _state.update {
            it.copy(step = BookingFlowUiState.Step.RESULTS, isLoading = true, errorCode = null)
        }
        viewModelScope.launch {
            when (
                val result = bookings.searchTrips(
                    originStationId = station.id,
                    destinationId = destination.id,
                    seatCount = current.seatCount,
                )
            ) {
                is ApiResult.Success -> _state.update {
                    it.copy(options = result.value, isLoading = false)
                }
                is ApiResult.Failure -> _state.update {
                    it.copy(options = emptyList()).failed(result.error)
                }
            }
        }
    }

    private fun book(option: TripOption) {
        val current = _state.value
        val station = current.selectedStation ?: return
        val destination = current.selectedDestination ?: return
        if (current.isSubmitting) return

        _state.update { it.copy(isSubmitting = true, errorCode = null) }
        viewModelScope.launch {
            val result = bookings.book(
                tripId = option.tripId,
                seatCount = current.seatCount,
                pickupStationId = station.id,
                dropoffDestinationId = destination.id,
                idempotencyKey = IdempotencyKeys.forBooking(
                    tripId = option.tripId,
                    seatCount = current.seatCount,
                    stationId = station.id,
                    attemptId = current.attemptId,
                ),
            )
            when (result) {
                is ApiResult.Success -> {
                    _state.update {
                        it.copy(
                            isSubmitting = false,
                            confirmedBooking = result.value,
                            step = BookingFlowUiState.Step.CONFIRMED,
                        )
                    }
                    _effects.send(BookingEffect.Booked(result.value.id))
                }
                is ApiResult.Failure -> {
                    _state.update { it.copy(isSubmitting = false).failed(result.error) }
                    // Someone took the last seat between the search and the tap.
                    // Re-run the search so the list reflects reality rather than
                    // leaving a stale option the passenger will tap again.
                    if (result.error.code == "TRIP_SEATS_UNAVAILABLE") search()
                }
            }
        }
    }

    private fun goBack() {
        _state.update { current ->
            when (current.step) {
                BookingFlowUiState.Step.ORIGIN_DISTRICT -> current
                BookingFlowUiState.Step.ORIGIN_VILLAGE ->
                    current.copy(step = BookingFlowUiState.Step.ORIGIN_DISTRICT)
                BookingFlowUiState.Step.ORIGIN_STATION ->
                    current.copy(step = BookingFlowUiState.Step.ORIGIN_VILLAGE)
                BookingFlowUiState.Step.DESTINATION ->
                    current.copy(step = BookingFlowUiState.Step.ORIGIN_STATION)
                BookingFlowUiState.Step.RESULTS ->
                    current.copy(step = BookingFlowUiState.Step.DESTINATION)
                BookingFlowUiState.Step.CONFIRMED -> current
            }.copy(errorCode = null)
        }
    }

    private fun retry() {
        when (_state.value.step) {
            BookingFlowUiState.Step.ORIGIN_DISTRICT -> loadDistricts()
            BookingFlowUiState.Step.DESTINATION ->
                _state.value.selectedStation?.let(::chooseStation)
            BookingFlowUiState.Step.RESULTS -> search()
            else -> Unit
        }
    }

    private fun BookingFlowUiState.failed(error: ApiException) = copy(
        isLoading = false,
        isSubmitting = false,
        errorCode = error.code,
        errorContext = error.context,
    )
}
