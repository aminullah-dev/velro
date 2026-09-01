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
)

/** Faster than the booking page: this screen exists to watch a dot move. */
private const val POLL_SECONDS = 15L

@HiltViewModel
class TrackRideViewModel @Inject constructor(
    private val bookings: BookingRepository,
    private val geography: GeographyRepository,
    private val documents: DocumentRepository,
    savedState: SavedStateHandle,
) : ViewModel() {

    private val bookingId: String = checkNotNull(savedState["bookingId"])

    private val _state = MutableStateFlow(TrackRideUiState())
    val state: StateFlow<TrackRideUiState> = _state.asStateFlow()

    init {
        viewModelScope.launch {
            bookings.booking(bookingId).collect { booking ->
                val first = _state.value.booking == null
                _state.update { it.copy(booking = booking) }
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
                delay(POLL_SECONDS * 1000)
                _state.value.booking?.let { refreshLive(it) }
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
