package af.velro.feature.driver

import af.velro.data.sync.SyncQueue
import af.velro.data.repository.BookingRepository
import af.velro.data.api.ApiException
import af.velro.data.api.ApiResult
import af.velro.data.repository.CurrentAssignment
import af.velro.data.repository.NegotiationRepository
import af.velro.domain.RideRequest
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
    /**
     * How many passengers are waiting, whether or not he is online.
     *
     * Fetched off-shift on purpose. Everything else here is gated on being
     * online, which is right for *doing* work and wrong for *knowing there is
     * any*: an offline driver saw a switch and his earnings and nothing else,
     * while somebody stood at a station with an open request thirty seconds
     * old. He had no way to find out that turning the switch on would show
     * him a fare.
     */
    val waiting: List<RideRequest> = emptyList(),

    val isLoading: Boolean = true,
    /**
     * A refresh the driver pulled for.
     *
     * Distinct from [isLoading], which only covers the case where there is no
     * profile yet and the screen is genuinely blank. A driver watching for
     * work must keep the board he is reading while it updates.
     */
    val isRefreshing: Boolean = false,
    /**
     * Bookings this driver has already scored, so the stars do not invite a
     * second attempt the server will refuse.
     *
     * Kept in memory only. It is a guard against a double tap, not a record --
     * the record is the rating row, and the server is the thing that enforces
     * one per trip.
     */
    val ratedBookings: Set<String> = emptySet(),
    val isBusy: Boolean = false,
    /**
     * The last work read did not fully succeed, so what is on screen is older
     * than it looks. Not an error page -- the board is still usable -- but the
     * difference between "nobody is waiting" and "I could not ask".
     */
    val isStale: Boolean = false,
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

    /**
     * The same reload, keeping the screen on show.
     *
     * Its own event rather than a flag, so the error state's retry -- which
     * has nothing to preserve and should blank -- cannot be confused with it.
     */
    data object PullToRefresh : DriverHomeEvent
    data object ToggleOnline : DriverHomeEvent
    data class AcceptOffer(val tripId: String) : DriverHomeEvent
    data object AdvanceTrip : DriverHomeEvent
    data class CancelTrip(val reasonCode: String, val note: String?) : DriverHomeEvent
    data class VerifyCodeChanged(val value: String) : DriverHomeEvent

    /**
     * Score the passenger who has just travelled.
     *
     * Carries the booking rather than the person: a car holds three riders and
     * the server needs to know which of them is being rated.
     */
    data class RatePassenger(val bookingId: String, val score: Int) : DriverHomeEvent
    data object VerifyPassenger : DriverHomeEvent
    data object DismissError : DriverHomeEvent
    data object MarkNotificationsRead : DriverHomeEvent
}

sealed interface DriverHomeEffect {
    data class TripCompleted(val earning: MoneyValue?) : DriverHomeEffect
    data class PassengerBoarded(val name: String?) : DriverHomeEffect

    /**
     * New work appeared while he had the app open.
     *
     * An effect rather than state, because it must fire once per arrival. A
     * boolean in state would replay on every rotation and ring at him for a
     * request he already saw.
     */
    data class RequestsArrived(val count: Int) : DriverHomeEffect
}

/** Often enough to feel live, rarely enough not to drain a phone or a data bundle. */
private const val POLL_SECONDS = 10L

@HiltViewModel
class DriverHomeViewModel @Inject constructor(
    private val notifications: NotificationRepository,
    private val drivers: DriverRepository,
    private val negotiation: NegotiationRepository,
    private val bookings: BookingRepository,
    private val queue: SyncQueue,
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
                // An approved driver who is offline is still worth asking,
                // because the answer is "somebody is waiting" and that is the
                // one thing that would make him go online.
                val worthAsking = current.assignment != null ||
                    current.profile?.canWork == true
                if (worthAsking) {
                    loadWork()
                } else if (current.profile != null) {
                    // A driver waiting to be approved is waiting for exactly
                    // one thing, and it arrives on his profile. Without this
                    // the loop spun doing nothing and approval never reached
                    // his screen: the only Refresh event is on the failed-load
                    // branch, which an applied-but-unapproved driver is not on,
                    // so he had to force-quit the app to find out he could
                    // work. Just the profile -- there is no board for him yet.
                    refreshProfileOnly()
                }
            }
        }
    }

    /** The one call an unapproved driver is waiting on. */
    private suspend fun refreshProfileOnly() {
        (drivers.profile() as? ApiResult.Success<DriverProfile>)?.let { profile ->
            _state.update { it.copy(profile = profile.value) }
        }
    }

    fun onEvent(event: DriverHomeEvent) {
        when (event) {
            DriverHomeEvent.Refresh -> refresh()
            DriverHomeEvent.PullToRefresh -> refresh(pulled = true)
            is DriverHomeEvent.RatePassenger -> ratePassenger(event.bookingId, event.score)
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

    private fun ratePassenger(bookingId: String, score: Int) {
        val tripId = _state.value.assignment?.trip?.id ?: return
        if (bookingId in _state.value.ratedBookings) return
        // Marked before the call, not after: the stars are a tap target and a
        // second tap while the first is in flight would be refused by the
        // server as a duplicate, which would surface as an error for something
        // the driver did successfully.
        _state.update { it.copy(ratedBookings = it.ratedBookings + bookingId) }
        viewModelScope.launch {
            when (val result = bookings.rate(tripId, score, bookingId = bookingId)) {
                is ApiResult.Success -> Unit
                is ApiResult.Failure ->
                    if (result.error.code == ApiException.OFFLINE) {
                        // Queued instead of un-marked: he did give the score,
                        // and it will land with the connection. The mark stays
                        // so the stars do not invite a second attempt.
                        queue.enqueueRating(tripId, score, comment = null, bookingId = bookingId)
                    } else {
                        // Let him try again. A score that did not land is worse
                        // than no score, because he believes he gave it.
                        _state.update { it.copy(ratedBookings = it.ratedBookings - bookingId) }
                    }
            }
        }
    }

    private fun refresh(pulled: Boolean = false) {
        _state.update {
            it.copy(
                // A pull never blanks the screen, even on a cold profile: the
                // indicator is already saying something is happening.
                isLoading = !pulled && _state.value.profile == null,
                isRefreshing = pulled,
                errorCode = null,
            )
        }
        viewModelScope.launch {
            when (val profile = drivers.profile()) {
                is ApiResult.Success -> {
                    _state.update { it.copy(profile = profile.value, isLoading = false) }
                    // loadWork is the rest of the screen -- the board, the
                    // assignment, the wallet. Awaited before the indicator
                    // stops, or it disappears while most of what the driver
                    // pulled for is still in flight.
                    loadWork()
                }
                is ApiResult.Failure -> _state.update { it.failed(profile.error) }
            }
            // Both paths, or a driver with no signal keeps a spinning
            // indicator for as long as he stays on the screen.
            _state.update { it.copy(isRefreshing = false) }
        }
    }

    private suspend fun loadWork() {
        // Failures are counted, not discarded.
        //
        // All five reads below used `as? ApiResult.Success`, so a driver on a
        // weak connection kept the board he had: no error, no marker, nothing
        // to refresh. He would sit looking at "nobody is waiting" that had
        // stopped being true twenty minutes earlier, and decide there was no
        // work today. The screen says so now, the way the booking detail
        // already does.
        var failed = false
        fun <T> record(result: ApiResult<T>): ApiResult<T> {
            if (result !is ApiResult.Success) failed = true
            return result
        }

        // The inbox first: it is the only thing that says a bid was accepted,
        // and it is one small read.
        (record(notifications.inbox(limit = 20)) as? ApiResult.Success)?.let { inbox ->
            _state.update { it.copy(inbox = inbox.value) }
        }
        (record(drivers.currentTrip()) as? ApiResult.Success)?.let { current ->
            _state.update { it.copy(assignment = current.value) }
        }
        // Offers are only worth fetching when there is no trip in flight.
        if (_state.value.assignment == null && _state.value.isOnline) {
            (record(drivers.offers()) as? ApiResult.Success)?.let { offers ->
                _state.update { it.copy(offers = offers.value) }
            }
        }
        // Not gated on being online. One small read, and it is the only thing
        // that turns "you are offline" from a status into a reason to act.
        if (_state.value.assignment == null) {
            (record(negotiation.openRequests()) as? ApiResult.Success)?.let { fetched ->
                val previous = _state.value.waiting.map { it.id }.toSet()
                val arrived = fetched.value.filter { it.id !in previous }
                _state.update { it.copy(waiting = fetched.value) }
                // Something new, and he is in a position to take it. There is
                // no push transport, so this ring is the only thing standing
                // between a request and a driver who is looking at his lap.
                if (arrived.isNotEmpty() && _state.value.isOnline) {
                    _effects.send(DriverHomeEffect.RequestsArrived(arrived.size))
                }
            }
        }
        (record(drivers.earnings()) as? ApiResult.Success)?.let { earnings ->
            _state.update { it.copy(earnings = earnings.value) }
        }
        _state.update { it.copy(isStale = failed) }
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
