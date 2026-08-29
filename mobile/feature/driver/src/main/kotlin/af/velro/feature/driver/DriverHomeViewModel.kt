package af.velro.feature.driver

import af.velro.data.api.ApiException
import af.velro.data.api.ApiResult
import af.velro.data.repository.CurrentAssignment
import af.velro.data.repository.DriverRepository
import af.velro.domain.DriverAvailability
import af.velro.domain.DriverProfile
import af.velro.domain.Earnings
import af.velro.domain.Lifecycles
import af.velro.domain.MoneyValue
import af.velro.domain.TripStatus
import af.velro.domain.TripSummary
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * The driver's working screen, section 74.
 *
 * Online/offline, the current trip, offers, and today's earnings -- nothing
 * else. A driver looks at this between passengers, often while parked in the
 * sun, so it shows the one action that matters right now rather than a menu.
 */
data class DriverHomeUiState(
    val profile: DriverProfile? = null,
    val assignment: CurrentAssignment? = null,
    val offers: List<TripSummary> = emptyList(),
    val earnings: Earnings? = null,

    val isLoading: Boolean = true,
    val isBusy: Boolean = false,
    val errorCode: String? = null,
    val errorContext: Map<String, Any?> = emptyMap(),

    val verifyingCode: String = "",
    val lastVerified: String? = null,
    val lastEarning: MoneyValue? = null,
) {
    val canWork: Boolean get() = profile?.canWork == true
    val isOnline: Boolean get() = profile?.isOnline == true

    /**
     * The single next step, derived from the transition table rather than from
     * a chain of `if`s on the screen.
     *
     * A button that the server would refuse is never offered.
     */
    val nextStep: TripStatus?
        get() {
            val status = assignment?.trip?.status ?: return null
            val candidate = when (status) {
                TripStatus.DRIVER_ASSIGNED -> TripStatus.DRIVER_ARRIVING
                TripStatus.DRIVER_ARRIVING -> TripStatus.ARRIVED_AT_PICKUP
                TripStatus.ARRIVED_AT_PICKUP -> TripStatus.BOARDING
                TripStatus.BOARDING -> TripStatus.IN_TRANSIT
                TripStatus.IN_TRANSIT -> TripStatus.ARRIVED
                TripStatus.ARRIVED -> TripStatus.COMPLETED
                else -> null
            } ?: return null
            return candidate.takeIf { Lifecycles.trip.can(status, it) }
        }

    /** Boarding is the only point at which checking a code makes sense. */
    val canVerifyPassenger: Boolean
        get() = assignment?.trip?.status in setOf(
            TripStatus.ARRIVED_AT_PICKUP, TripStatus.BOARDING,
        )
}

sealed interface DriverHomeEvent {
    data object Refresh : DriverHomeEvent
    data object ToggleOnline : DriverHomeEvent
    data class AcceptOffer(val tripId: String) : DriverHomeEvent
    data object AdvanceTrip : DriverHomeEvent
    data class VerifyCodeChanged(val value: String) : DriverHomeEvent
    data object VerifyPassenger : DriverHomeEvent
    data object DismissError : DriverHomeEvent
}

sealed interface DriverHomeEffect {
    data class TripCompleted(val earning: MoneyValue?) : DriverHomeEffect
    data class PassengerBoarded(val name: String?) : DriverHomeEffect
}

@HiltViewModel
class DriverHomeViewModel @Inject constructor(
    private val drivers: DriverRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(DriverHomeUiState())
    val state: StateFlow<DriverHomeUiState> = _state.asStateFlow()

    private val _effects = Channel<DriverHomeEffect>(Channel.BUFFERED)
    val effects = _effects.receiveAsFlow()

    init {
        refresh()
    }

    fun onEvent(event: DriverHomeEvent) {
        when (event) {
            DriverHomeEvent.Refresh -> refresh()
            DriverHomeEvent.ToggleOnline -> toggleOnline()
            is DriverHomeEvent.AcceptOffer -> accept(event.tripId)
            DriverHomeEvent.AdvanceTrip -> advance()
            is DriverHomeEvent.VerifyCodeChanged ->
                _state.update { it.copy(verifyingCode = event.value.take(8), errorCode = null) }
            DriverHomeEvent.VerifyPassenger -> verify()
            DriverHomeEvent.DismissError -> _state.update { it.copy(errorCode = null) }
        }
    }

    private fun refresh() {
        _state.update { it.copy(isLoading = _state.value.profile == null, errorCode = null) }
        viewModelScope.launch {
            when (val profile = drivers.profile()) {
                is ApiResult.Success -> {
                    _state.update { it.copy(profile = profile.value, isLoading = false) }
                    loadWork()
                }
                is ApiResult.Failure -> _state.update { it.failed(profile.error) }
            }
        }
    }

    private suspend fun loadWork() {
        (drivers.currentTrip() as? ApiResult.Success)?.let { current ->
            _state.update { it.copy(assignment = current.value) }
        }
        // Offers are only worth fetching when there is no trip in flight.
        if (_state.value.assignment == null && _state.value.isOnline) {
            (drivers.offers() as? ApiResult.Success)?.let { offers ->
                _state.update { it.copy(offers = offers.value) }
            }
        }
        (drivers.earnings() as? ApiResult.Success)?.let { earnings ->
            _state.update { it.copy(earnings = earnings.value) }
        }
    }

    private fun toggleOnline() {
        val profile = _state.value.profile ?: return
        // The approval gate is checked here so the app can explain why, rather
        // than sending a request that will be refused.
        if (!profile.canWork) {
            _state.update { it.copy(errorCode = "DRIVER_NOT_APPROVED") }
            return
        }
        val target =
            if (profile.isOnline) DriverAvailability.OFFLINE else DriverAvailability.ONLINE

        _state.update { it.copy(isBusy = true, errorCode = null) }
        viewModelScope.launch {
            when (val result = drivers.setAvailability(target)) {
                is ApiResult.Success -> {
                    _state.update { it.copy(isBusy = false) }
                    refresh()
                }
                is ApiResult.Failure ->
                    _state.update { it.copy(isBusy = false).failed(result.error) }
            }
        }
    }

    private fun accept(tripId: String) {
        val driverId = _state.value.profile?.id ?: return
        _state.update { it.copy(isBusy = true, errorCode = null) }
        viewModelScope.launch {
            when (val result = drivers.accept(tripId, driverId)) {
                is ApiResult.Success -> {
                    _state.update { it.copy(isBusy = false, offers = emptyList()) }
                    refresh()
                }
                is ApiResult.Failure -> {
                    _state.update { it.copy(isBusy = false).failed(result.error) }
                    // Another driver got there first; drop the stale offer so it
                    // cannot be tapped again.
                    if (result.error.code == "TRIP_DRIVER_ALREADY_ASSIGNED") refresh()
                }
            }
        }
    }

    private fun advance() {
        val current = _state.value
        val trip = current.assignment?.trip ?: return
        val target = current.nextStep ?: return

        _state.update { it.copy(isBusy = true, errorCode = null) }
        viewModelScope.launch {
            when (val result = drivers.advance(trip.id, trip.status, target)) {
                is ApiResult.Success -> {
                    val outcome = result.value
                    _state.update { it.copy(isBusy = false, lastEarning = outcome.driverEarning) }
                    if (outcome.status == TripStatus.COMPLETED) {
                        _effects.send(DriverHomeEffect.TripCompleted(outcome.driverEarning))
                    }
                    refresh()
                }
                is ApiResult.Failure -> {
                    _state.update { it.copy(isBusy = false).failed(result.error) }
                    // The app's view of the trip was stale; re-read rather than
                    // leaving a button that will keep failing.
                    if (result.error.code == "TRIP_INVALID_TRANSITION") refresh()
                }
            }
        }
    }

    private fun verify() {
        val trip = _state.value.assignment?.trip ?: return
        val code = _state.value.verifyingCode.trim()
        if (code.length < 3) return

        _state.update { it.copy(isBusy = true, errorCode = null) }
        viewModelScope.launch {
            when (val result = drivers.verifyPassenger(trip.id, code)) {
                is ApiResult.Success -> {
                    _state.update {
                        it.copy(
                            isBusy = false,
                            verifyingCode = "",
                            lastVerified = result.value.bookingNumber,
                        )
                    }
                    _effects.send(DriverHomeEffect.PassengerBoarded(result.value.passengerName))
                    refresh()
                }
                is ApiResult.Failure -> _state.update {
                    // Clear the field on a bad code: the driver retypes rather
                    // than editing a wrong value on a small keyboard.
                    it.copy(isBusy = false, verifyingCode = "").failed(result.error)
                }
            }
        }
    }

    private fun DriverHomeUiState.failed(error: ApiException) = copy(
        isLoading = false,
        isBusy = false,
        errorCode = error.code,
        errorContext = error.context,
    )
}
