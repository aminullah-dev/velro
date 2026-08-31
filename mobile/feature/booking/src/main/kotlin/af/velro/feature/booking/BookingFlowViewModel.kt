package af.velro.feature.booking

import af.velro.data.sync.SyncQueue
import af.velro.data.api.ApiException
import af.velro.data.api.ApiResult
import af.velro.data.api.IdempotencyKeys
import af.velro.data.repository.BookingRepository
import af.velro.core.i18n.Numerals
import af.velro.data.repository.GeographyRepository
import af.velro.data.repository.NegotiationRepository
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
import af.velro.core.i18n.Calendars
import java.time.Instant
import java.time.LocalDate
import java.time.LocalTime
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
/**
 * Departure hours offered, and the one selected by default.
 *
 * Cars out of Ghorband leave early; nothing sensible departs at two in the
 * morning, and offering twenty-four rows of hours to scroll is a worse
 * instrument than offering the sixteen anyone would use.
 */
private const val EARLIEST_DEPARTURE_HOUR = 4
private const val LATEST_DEPARTURE_HOUR = 20
private const val DEFAULT_DEPARTURE_HOUR = 6
// Coming back is an afternoon thing far more often than a dawn one.
private const val DEFAULT_RETURN_HOUR = 14

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
    /**
     * The request was saved for later, not sent.
     *
     * Its own flag rather than a step: CONFIRMED means a seat exists, and this
     * means precisely that one does not yet. The two must be impossible to
     * mistake for each other on screen.
     */
    val queuedOffline: Boolean = false,
    /** What the passenger is willing to pay, as they typed it. */
    val offeredFare: String = "",
    val note: String = "",
    /** The return leg's fare, as typed. Only meaningful with a return chosen. */
    val returnFare: String = "",

    /**
     * Which day the journey is for: null for now, 0 today, 1 tomorrow, 2 the
     * day after.
     *
     * Days rather than a date, and an hour rather than a time, because this is
     * chosen at a roadside by somebody who may not read well. A calendar in
     * Hijri Shamsi, in an RTL dialog, is the wrong instrument for "tomorrow
     * morning" -- and "tomorrow morning" is how every one of these journeys is
     * actually arranged.
     */
    val departureDay: Int? = null,
    val departureHour: Int = DEFAULT_DEPARTURE_HOUR,
    /**
     * The hour it is in Ghorband, held on the state so the hour rules can be
     * tested at six in the evening without waiting until six in the evening.
     * Refreshed whenever the flow reaches the ask step.
     */
    val nowHour: Int = LocalTime.now(Calendars.KABUL).hour,

    /**
     * Days after the outbound to come back, or null for one way.
     *
     * Counted from the departure rather than from today, because that is how
     * the journey is described: "back the day after", not "back on the
     * fourteenth". Ghorband returns are usually not the same day -- a car to
     * Kabul goes today and comes back tomorrow or later -- so 0 is offered but
     * is not the default.
     */
    val returnAfterDays: Int? = null,
    val returnHour: Int = DEFAULT_RETURN_HOUR,
    val askedRequestId: String? = null,
) {
    enum class Step {
        ORIGIN_DISTRICT, ORIGIN_VILLAGE, ORIGIN_STATION,
        // Section 89: after choosing where, the passenger names a price. There
        // is no results step to reach first -- VELRO has no price to show.
        DESTINATION, ASK, RESULTS, CONFIRMED,
    }

    val canSearch: Boolean get() = selectedStation != null && selectedDestination != null

    /** Whole afghani as typed; converted to minor units only when sent. */
    val fareMinor: Long? get() = offeredFare.toLongOrNull()?.takeIf { it > 0 }?.times(100)

    /** The return leg's fare, or null when there is no return to price. */
    val returnFareMinor: Long?
        get() =
            if (returnAfterDays == null) null
            else returnFare.toLongOrNull()?.takeIf { it > 0 }?.times(100)

    /**
     * What the journey costs altogether, for the line under the two fields.
     *
     * Shown because the passenger is naming a number they will hand over in
     * cash, and two numbers on a screen are not the number in the hand.
     */
    val totalFareMinor: Long?
        // Null until every chosen leg has a price on it.
        //
        // An unpriced return counted as zero, so the moment the outbound fare
        // was typed the screen said "Total 300 AFN" for a round trip the
        // passenger had not finished pricing -- a number she might well send,
        // and the one figure on the screen she is actually deciding about.
        get() {
            val out = fareMinor ?: return null
            if (returnAfterDays != null && returnFareMinor == null) return null
            return out + (returnFareMinor ?: 0L)
        }

    /**
     * The chosen day and hour as an instant, or null for "now".
     *
     * Built in Kabul time, not the handset's zone, and deliberately: "six
     * tomorrow" means six in Ghorband. Calendars renders every departure in
     * Asia/Kabul, so a picker working in the device zone would disagree with
     * the screen that displays the result for anyone not in the country --
     * which includes the person testing this from Canada. Afghanistan is
     * UTC+04:30, and a half-hour offset is exactly the sort of thing that
     * silently becomes an hour wrong when the arithmetic is done by hand, so
     * it is not done by hand.
     */
    fun requestedFor(): Instant? {
        val day = departureDay ?: return null
        return LocalDate.now(Calendars.KABUL)
            .plusDays(day.toLong())
            .atTime(departureHour, 0)
            .atZone(Calendars.KABUL)
            .toInstant()
    }

    /**
     * The return leg as an instant, or null for one way.
     *
     * Null whenever there is no departure day either: a return counted from
     * "now" would be counted from nothing.
     */
    fun returnFor(): Instant? {
        val out = departureDay ?: return null
        val after = returnAfterDays ?: return null
        return LocalDate.now(Calendars.KABUL)
            .plusDays((out + after).toLong())
            .atTime(returnHour, 0)
            .atZone(Calendars.KABUL)
            .toInstant()
    }

    /**
     * The same state with both chosen hours inside the hours actually offered.
     *
     * The day chips carry the existing hour through, and the hours on offer
     * change with the day -- so at six in the evening, tapping "today" left the
     * six-o'clock default selected while the row showed 19:00 and 20:00. No
     * chip appeared chosen, and "ask for a car" sent this morning: refused,
     * every time, with a message about a time in the past that the passenger
     * never picked.
     *
     * The return has the same shape: a same-day return must leave after the
     * outbound, so moving the outbound to 19:00 leaves a 14:00 return behind
     * it, which the server refuses for a different reason.
     */
    fun withHoursInRange(): BookingFlowUiState {
        val out = departureHours
        val moved =
            if (out.isEmpty() || departureHour in out) this
            else copy(departureHour = out.first())
        val back = moved.returnHours
        return if (back.isEmpty() || moved.returnHour in back) moved
        else moved.copy(returnHour = back.first())
    }

    /**
     * The hours worth offering for the return leg.
     *
     * A same-day return must leave after the outbound does, so those hours
     * start above the departure hour; on any later day the whole range is
     * open. Reusing the outbound's list here would have offered a six o'clock
     * return on a six o'clock departure -- a request the server refuses, and
     * being refused for choosing what the app offered is worse than never
     * being offered it.
     *
     * A return landing on today is impossible to reach: the earliest departure
     * is today, and a same-day return must be later than it.
     */
    val returnHours: List<Int>
        get() {
            val first =
                if (returnAfterDays == 0) departureHour + 1 else EARLIEST_DEPARTURE_HOUR
            return (maxOf(first, EARLIEST_DEPARTURE_HOUR)..LATEST_DEPARTURE_HOUR).toList()
        }

    /**
     * The hours still worth offering for the chosen day.
     *
     * Today's list starts after the current hour: showing four in the morning
     * at six in the evening invites a choice the server will refuse, and being
     * refused for picking something the app offered is worse than not being
     * offered it.
     */
    val departureHours: List<Int>
        get() {
            val first =
                if (departureDay == 0)
                    maxOf(EARLIEST_DEPARTURE_HOUR, nowHour + 1)
                else EARLIEST_DEPARTURE_HOUR
            return (first..LATEST_DEPARTURE_HOUR).toList()
        }

    val canAsk: Boolean
        // A chosen return with no price on it is an unfinished ask, not a one
        // way journey: sending it would put a request on the board that no
        // driver can answer, because the server requires both legs or neither.
        get() = canSearch && fareMinor != null && !isSubmitting &&
            (returnAfterDays == null || returnFareMinor != null) &&
            // A day with no hours left on it -- "today", once the last
            // departure has gone -- cannot be asked for. The picker already
            // says so; this is what stops the button sending it anyway.
            (departureDay == null || departureHours.isNotEmpty()) &&
            (returnAfterDays == null || returnHours.isNotEmpty())
}

sealed interface BookingEvent {
    data class DistrictChosen(val district: District) : BookingEvent
    data class VillageChosen(val village: Village) : BookingEvent
    data class StationChosen(val station: Station) : BookingEvent
    data class GroupToggled(val groupId: String) : BookingEvent
    data class DestinationChosen(val destination: Destination) : BookingEvent
    data class SeatCountChanged(val count: Int) : BookingEvent
    data class FareChanged(val text: String) : BookingEvent
    data class NoteChanged(val text: String) : BookingEvent
    data class ReturnFareChanged(val value: String) : BookingEvent
    data class DepartureChanged(val day: Int?, val hour: Int) : BookingEvent
    data class ReturnChanged(val afterDays: Int?, val hour: Int) : BookingEvent
    data object AskForRide : BookingEvent
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
    private val negotiation: NegotiationRepository,
    private val queue: SyncQueue,
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
                // The hour is re-read here rather than at construction: the
                // flow can sit on the destination list while the evening turns
                // over, and the hours offered on the next screen are computed
                // from it.
                it.copy(
                    selectedDestination = event.destination,
                    step = BookingFlowUiState.Step.ASK,
                    nowHour = LocalTime.now(Calendars.KABUL).hour,
                    errorCode = null,
                ).withHoursInRange()
            }
            is BookingEvent.SeatCountChanged -> _state.update {
                it.copy(seatCount = event.count.coerceIn(1, 4))
            }
            is BookingEvent.TripChosen -> book(event.option)
            is BookingEvent.FareChanged -> _state.update {
                it.copy(offeredFare = Numerals.latin(event.text).filter(Char::isDigit))
            }
            is BookingEvent.NoteChanged -> _state.update { it.copy(note = event.text) }

            is BookingEvent.DepartureChanged -> _state.update {
                // A return is relative to the outbound, so moving the outbound
                // to "now" takes the return with it: "back two days after"
                // means nothing once there is no departure day to count from.
                it.copy(
                    departureDay = event.day,
                    departureHour = event.hour,
                    returnAfterDays = if (event.day == null) null else it.returnAfterDays,
                )
            }

            is BookingEvent.ReturnFareChanged -> _state.update {
                it.copy(returnFare = event.value, errorCode = null)
            }

            is BookingEvent.ReturnChanged -> _state.update {
                it.copy(returnAfterDays = event.afterDays, returnHour = event.hour)
            }
            BookingEvent.AskForRide -> ask()
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

    private fun ask() {
        val current = _state.value
        val station = current.selectedStation ?: return
        val destination = current.selectedDestination ?: return
        val minor = current.fareMinor ?: return
        if (current.isSubmitting) return

        _state.update { it.copy(isSubmitting = true, errorCode = null) }
        viewModelScope.launch {
            val result = negotiation.ask(
                originStationId = station.id,
                destinationId = destination.id,
                passengerCount = current.seatCount,
                offeredFareMinor = minor,
                note = current.note,
                requestedFor = current.requestedFor(),
                returnFor = current.returnFor(),
                returnFareMinor = current.returnFareMinor,
            )
            when (result) {
                is ApiResult.Success -> _state.update {
                    it.copy(isSubmitting = false, askedRequestId = result.value.id)
                }
                is ApiResult.Failure -> _state.update {
                    it.copy(isSubmitting = false).failed(result.error)
                }
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
                    if (result.error.code == ApiException.OFFLINE) {
                        // Saved, honestly. The same deterministic key goes into
                        // the queue, so if the request in fact reached the
                        // server before the connection died, the replay gets
                        // the original answer instead of a second seat.
                        queue.enqueueBooking(
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
                        _state.update {
                            it.copy(isSubmitting = false, queuedOffline = true)
                        }
                        return@launch
                    }
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
                BookingFlowUiState.Step.ASK ->
                    // Back clears the price: a number typed for one destination
                    // must not silently become the offer for another.
                    //
                    // The return was left behind when it was added -- so a
                    // fare typed for the way back from Kabul survived onto a
                    // journey to Charikar, and so did the day it was for.
                    current.copy(
                        step = BookingFlowUiState.Step.DESTINATION,
                        offeredFare = "",
                        note = "",
                        returnFare = "",
                        returnAfterDays = null,
                    )
                BookingFlowUiState.Step.RESULTS ->
                    current.copy(step = BookingFlowUiState.Step.ASK)
                BookingFlowUiState.Step.CONFIRMED -> current
            }.copy(errorCode = null)
        }
    }

    private fun retry() {
        val current = _state.value
        when (current.step) {
            BookingFlowUiState.Step.ORIGIN_DISTRICT -> loadDistricts()
            // The two steps that had no retry at all. Both read from the Room
            // cache, so on a phone that has never had signal they are exactly
            // the steps most likely to be empty -- and the only ones where a
            // passenger could reach a dead end with nothing to press.
            BookingFlowUiState.Step.ORIGIN_VILLAGE ->
                current.selectedDistrict?.let(::chooseDistrict)
            BookingFlowUiState.Step.ORIGIN_STATION ->
                current.selectedVillage?.let(::chooseVillage)
            BookingFlowUiState.Step.DESTINATION ->
                current.selectedStation?.let(::chooseStation)
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
