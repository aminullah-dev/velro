package af.velro.feature.trip

import af.velro.data.api.ApiResult
import af.velro.data.repository.BookingRepository
import af.velro.data.repository.DocumentRepository
import af.velro.data.repository.GeographyRepository
import af.velro.data.repository.MapPlace
import af.velro.data.repository.RideDriver
import af.velro.data.repository.TripMapData
import af.velro.data.tracking.Eta
import af.velro.domain.Booking
import af.velro.domain.BookingStatus
import af.velro.feature.safety.RideFacts
import androidx.lifecycle.SavedStateHandle
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

data class TrackRideUiState(
    val booking: Booking? = null,
    val journeyMap: TripMapData? = null,
    val driver: RideDriver? = null,
    val driverPhoto: ByteArray? = null,
    val vehicle: MapPlace? = null,
    val vehicleAgeSeconds: Int? = null,
    val etaMinutes: Int? = null,
    /** Her own name, for the foot of the ride map. */
    val passengerName: String? = null,
    /** She was on board and is no longer: the ride is over. */
    val rideEnded: Boolean = false,
) {
    /**
     * On board: the screen becomes the ride map, the same moment the
     * driver's phone does.
     */
    val isRiding: Boolean get() = booking?.status == BookingStatus.ONBOARD

    /** The road's next warning ahead of the car, for the top of the ride map. */
    val roadAhead: af.velro.data.tracking.RoadAhead.Next?
        get() {
            val map = journeyMap ?: return null
            val car = vehicle ?: return null
            return af.velro.data.tracking.RoadAhead.next(
                map.geometry.orEmpty(), car.latitude to car.longitude, map.alerts,
            )
        }

    /**
     * What the help sheet reads down a phone line (ADR 0010), from whichever
     * copy this screen holds is freshest.
     *
     * The live driver card wins when it has arrived: a driver assigned or
     * changed mid-wait reaches it on the next poll, while the cached booking
     * row keeps saying what it said until something refreshes it. Until the
     * card arrives the booking's own copy stands in, so the sheet never knows
     * less than the booking page the passenger just came from.
     *
     * One car, one source. When the live card is present its name, number
     * and plate are taken together, gaps included, rather than patched from
     * the booking: after a reassignment those are a different man's name
     * beside a different car's plate, and a relative sent that pair would be
     * looking for a car that is not coming.
     *
     * The journey's ends come off the drawn map, and off the booking when
     * there is no map to draw. They are the same two places either way.
     */
    val helpFacts: RideFacts?
        get() {
            val b = booking ?: return null
            val live = driver
            return RideFacts(
                bookingNumber = b.number,
                driverName = if (live == null) b.driverName else live.name,
                driverPhone = if (live == null) b.driverPhone else live.phone,
                plate = if (live == null) b.vehiclePlate else live.vehicle?.plateNumber,
                origin = journeyMap?.origin?.name ?: b.pickupStationName,
                destination = journeyMap?.destination?.name ?: b.dropoffDestinationName,
            )
        }
}

/** Faster than the booking page: this screen exists to watch a dot move. */
private const val POLL_SECONDS = 15L
private const val RIDING_POLL_MS = 8_000L

@HiltViewModel
class TrackRideViewModel @Inject constructor(
    private val bookings: BookingRepository,
    private val geography: GeographyRepository,
    private val documents: DocumentRepository,
    private val auth: af.velro.data.repository.AuthRepository,
    savedState: SavedStateHandle,
) : ViewModel() {

    private val bookingId: String = checkNotNull(savedState["bookingId"])

    private val _state = MutableStateFlow(TrackRideUiState())
    val state: StateFlow<TrackRideUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            (auth.profile() as? ApiResult.Success)?.value?.let { me ->
                _state.update { it.copy(passengerName = me.fullName) }
            }
        }
        viewModelScope.launch {
            bookings.booking(bookingId).collect { booking ->
                val first = _state.value.booking == null
                _state.update {
                    val ended = it.booking?.status == BookingStatus.ONBOARD &&
                        booking != null && booking.status != BookingStatus.ONBOARD
                    it.copy(booking = booking, rideEnded = it.rideEnded || ended)
                }
                if (booking != null && first) {
                    // The cache emits a moment after this screen opens, and
                    // the poll below had already fired against a null
                    // booking by then -- leaving "waiting for the car's
                    // position" on screen for a full cycle, on the one
                    // screen whose entire job is to answer that question
                    // now. So the first arrival draws immediately.
                    loadOnce(booking)
                    refreshLive(booking)
                }
            }
        }
        viewModelScope.launch {
            while (isActive) {
                // Faster on board, where the warning at the top follows the car.
                delay(if (_state.value.isRiding) RIDING_POLL_MS else POLL_SECONDS * 1000)
                _state.value.booking?.let { booking ->
                    // The cached row only moves when something refreshes it,
                    // and the end of the ride is news this screen must hear.
                    bookings.refreshBooking(booking.id)
                    refreshLive(booking)
                }
            }
        }
    }

    private suspend fun loadOnce(booking: Booking) {
        (geography.journeyMap(
            booking.pickupStationId, booking.dropoffDestinationId,
        ) as? ApiResult.Success)?.let { drawn ->
            _state.update { it.copy(journeyMap = drawn.value) }
        }
        (bookings.rideDriver(bookingId) as? ApiResult.Success)?.value?.let { driver ->
            _state.update { it.copy(driver = driver) }
            documents.driverPhoto(driver.driverId)?.let { photo ->
                _state.update { it.copy(driverPhoto = photo) }
            }
        }
    }

    private suspend fun refreshLive(booking: Booking) {
        // The driver card can arrive late (assignment happens mid-wait).
        if (_state.value.driver == null) {
            (bookings.rideDriver(bookingId) as? ApiResult.Success)?.value?.let { driver ->
                _state.update { it.copy(driver = driver) }
                documents.driverPhoto(driver.driverId)?.let { photo ->
                    _state.update { it.copy(driverPhoto = photo) }
                }
            }
        }
        val ping = (bookings.vehicleLocation(bookingId) as? ApiResult.Success)?.value
        val map = _state.value.journeyMap
        val road = map?.geometry
        val eta = if (ping != null && road != null) {
            // Before she boards the car is coming to her station; after, they
            // are both going to the destination. The road is the same line.
            val target = if (booking.status == BookingStatus.ONBOARD) {
                map.destination
            } else {
                map.origin
            }
            target?.let {
                Eta.minutes(
                    geometry = road,
                    car = ping.latitude to ping.longitude,
                    target = it.latitude to it.longitude,
                    avgSpeedKmh = map.avgSpeedKmh,
                )
            }
        } else null
        _state.update {
            it.copy(
                vehicle = ping?.let { p -> MapPlace("", p.latitude, p.longitude) },
                vehicleAgeSeconds = ping?.ageSeconds,
                etaMinutes = eta,
            )
        }
    }
}
