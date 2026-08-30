package af.velro.feature.driver

import af.velro.data.api.ApiException
import af.velro.data.api.ApiResult
import af.velro.data.repository.CurrentAssignment
import af.velro.data.repository.NotificationRepository
import af.velro.data.repository.DriverRepository
import af.velro.domain.DriverAvailability
import af.velro.domain.NotificationInbox
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
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
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
    /** What the server has told this driver. Currently the only way they learn. */
    val inbox: NotificationInbox? = null,
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

    /**
     * Whether the driver may call this trip off.
     *
     * Asked of the shared lifecycle rather than listed here, so the app and the
     * server cannot disagree about it. IN_TRANSIT is not cancellable: once the
     * car is moving with someone in it, the journey finishes or it is an
     * incident, not a cancellation.
     */
    val canCancelTrip: Boolean
        get() {
            val status = assignment?.trip?.status ?: return false
            return Lifecycles.trip.can(status, TripStatus.CANCELLED)
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
    data class CancelTrip(val reasonCode: String, val note: String?) : DriverHomeEvent
    data class VerifyCodeChanged(val value: String) : DriverHomeEvent
    data object VerifyPassenger : DriverHomeEvent
    data object DismissError : DriverHomeEvent
    data object MarkNotificationsRead : DriverHomeEvent
}

sealed interface DriverHomeEffect {
    data class TripCompleted(val earning: MoneyValue?) : DriverHomeEffect
    data class PassengerBoarded(val name: String?) : DriverHomeEffect
}

/** Often enough to feel live, rarely enough not to drain a phone or a data bundle. */
private const val POLL_SECONDS = 10L

@HiltViewModel
class DriverHomeViewModel @Inject constructor(
    private val notifications: NotificationRepository,
    private val drivers: DriverRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(DriverHomeUiState())
    val state: StateFlow<DriverHomeUiState> = _state.asStateFlow()

    private val _effects = Channel<DriverHomeEffect>(Channel.BUFFERED)
    val effects = _effects.receiveAsFlow()

    init {
        refresh()
        poll()
    }

    /**
     * Keep looking, because nothing tells the driver otherwise.
     *
     * When a passenger accepts a bid the server writes notify.offer.accepted to
     * the driver's inbox -- and there is no push transport, so nothing wakes the
     * phone. Before this the screen loaded once in `init` and the ViewModel is
     * retained on the back stack, so a driver who bid from the board and came
     * back Home saw the same stale screen while a passenger stood at a station
     * waiting for them.
     *
     * Only while there is something to learn: an unapproved driver, or one who
     * is offline with no trip in flight, has nothing arriving and should not be
     * spending a data bundle to hear it.
     */
    private fun poll() {
        viewModelScope.launch {
            while (isActive) {
                delay(POLL_SECONDS * 1000)
                val current = _state.value
                val worthAsking = current.assignment != null ||
                    (current.profile?.canWork == true && current.isOnline)
                if (worthAsking) loadWork()
            }
        }
    }

    fun onEvent(event: DriverHomeEvent) {
        when (event) {
            DriverHomeEvent.Refresh -> refresh()
            DriverHomeEvent.ToggleOnline -> toggleOnline()
            is DriverHomeEvent.AcceptOffer -> accept(event.tripId)
            DriverHomeEvent.AdvanceTrip -> advance()
            is DriverHomeEvent.CancelTrip -> cancelTrip(event.reasonCode, event.note)
            is DriverHomeEvent.VerifyCodeChanged ->
                _state.update { it.copy(verifyingCode = event.value.take(8), errorCode = null) }
            DriverHomeEvent.VerifyPassenger -> verify()
            DriverHomeEvent.DismissError -> _state.update { it.copy(errorCode = null) }
            DriverHomeEvent.MarkNotificationsRead -> viewModelScope.launch {
                notifications.markRead()
                (notifications.inbox(limit = 20) as? ApiResult.Success)?.let { inbox ->
                    _state.update { it.copy(inbox = inbox.value) }
                }
            }
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
        // The inbox first: it is the only thing that says a bid was accepted,
        // and it is one small read.
        (notifications.inbox(limit = 20) as? ApiResult.Success)?.let { inbox ->
            _state.update { it.copy(inbox = inbox.value) }
        }
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

    /**
     * Call the trip off.
     *
     * A driver whose car breaks down at a pickup point had no action here at
     * all: the API accepted CANCELLED and the app only ever walked forward, so
     * the choice was drive the trip or abandon the passenger silently.
     */
    private fun cancelTrip(reasonCode: String, note: String?) {
        val assignment = _state.value.assignment ?: return
        _state.update { it.copy(isBusy = true, errorCode = null) }
        viewModelScope.launch {
            val result = drivers.advance(
                tripId = assignment.trip.id,
                from = assignment.trip.status,
                to = TripStatus.CANCELLED,
                reasonCode = reasonCode,
                note = note?.takeIf { it.isNotBlank() },
            )
            when (result) {
                is ApiResult.Success -> {
                    // The trip is gone, so the card must go with it -- and the
                    // driver is back to being available for work.
                    _state.update {
                        // lastVerified goes with the trip. Left set, a green
                        // tick from this morning's passenger appears above
                        // tonight's, and the driver boards the wrong person
                        // believing the code was checked.
                        it.copy(isBusy = false, assignment = null, lastVerified = null)
                    }
                    refresh()
                }
                is ApiResult.Failure ->
                    _state.update { it.copy(isBusy = false).failed(result.error) }
            }
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
                    // Same reason as cancelling: the tick belongs to the
                    // trip that was verified, not to the driver.
                    _state.update { it.copy(isBusy = false, lastVerified = null) }
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
