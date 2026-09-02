package af.velro.feature.trip

import af.velro.data.repository.MapPlace
import af.velro.data.repository.RideDriver
import af.velro.data.repository.RideVehicle
import af.velro.data.repository.TripMapData
import af.velro.domain.Booking
import af.velro.domain.BookingStatus
import af.velro.domain.MoneyValue
import af.velro.domain.PaymentMethod
import af.velro.domain.RideKind
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * What the help sheet is handed from the tracking screen (ADR 0010).
 *
 * `helpFacts` is a pure function of [TrackRideUiState], tested directly
 * rather than through the ViewModel, which needs a booking cache, a
 * geography cache and a document store to construct and has fakes for none
 * of them in this module.
 *
 * The property under test is which copy of each fact wins. The screen holds
 * two: the booking row, cached and possibly a poll behind, and the live
 * driver card fetched for this screen. A sheet that read the stale one would
 * have a woman reading a relative the wrong plate.
 */
class TrackRideUiStateTest {

    // The numbers below are the documented placeholder shape, not subscribers.
    private val booking = Booking(
        id = "01a05400-0000-7000-8000-0000000000b1",
        number = "BK-260902-0001",
        tripId = "01a05400-0000-7000-8000-0000000000a1",
        status = BookingStatus.ONBOARD,
        rideKind = RideKind.SHARED,
        seatCount = 1,
        seatNumbers = listOf(2),
        pickupStationId = "01a05400-0000-7000-8000-00000000000c",
        dropoffDestinationId = "01a05400-0000-7000-8000-00000000000d",
        fareTotal = MoneyValue(30000),
        paymentMethod = PaymentMethod.CASH,
        pickupStationName = "ایستگاه خیشکی",
        dropoffDestinationName = "چاریکار",
        driverName = "احمد",
        driverPhone = "+93700000000",
        vehiclePlate = "KBL 12345",
    )

    private val liveDriver = RideDriver(
        driverId = "01a05400-0000-7000-8000-0000000000d1",
        name = "محمود",
        phone = "+93700000009",
        ratingAverage = 4.8,
        ratingCount = 12,
        vehicle = RideVehicle(
            brand = "Toyota",
            model = "Corolla",
            colour = "سفید",
            plateNumber = "PRW 67890",
            seatCapacity = 4,
        ),
    )

    private val map = TripMapData(
        origin = MapPlace("ایستگاه خیشکی", 35.0, 69.0),
        destination = MapPlace("چاریکار", 35.1, 69.1),
        geometry = null,
        stations = emptyList(),
        attribution = "",
        styleUrl = "",
    )

    @Test
    fun `no booking, no facts`() {
        // RideFacts needs a booking number, and the sheet already has an
        // honest "no ride" line for a null ride. Inventing one would be worse.
        assertNull(TrackRideUiState().helpFacts)
        assertNull(TrackRideUiState(driver = liveDriver, journeyMap = map).helpFacts)
    }

    @Test
    fun `the booking alone is enough`() {
        // The cache emits the booking a moment before the driver call and
        // the map answer come back. The sheet must not know less than the
        // booking page the passenger just left.
        val facts = TrackRideUiState(booking = booking).helpFacts!!
        assertEquals("BK-260902-0001", facts.bookingNumber)
        assertEquals("احمد", facts.driverName)
        assertEquals("+93700000000", facts.driverPhone)
        assertEquals("KBL 12345", facts.plate)
        assertEquals("ایستگاه خیشکی", facts.origin)
        assertEquals("چاریکار", facts.destination)
    }

    @Test
    fun `the live driver card outranks the booking's cached copy`() {
        // A driver changed mid-wait reaches the live card on the next poll;
        // the booking row keeps naming the old one until something refreshes
        // it. The plate read down a phone line must be the car that is
        // actually coming.
        val facts = TrackRideUiState(booking = booking, driver = liveDriver).helpFacts!!
        assertEquals("محمود", facts.driverName)
        assertEquals("+93700000009", facts.driverPhone)
        assertEquals("PRW 67890", facts.plate)
    }

    @Test
    fun `a live card with gaps is not patched from the booking`() {
        // One car, one source. The old driver's name beside the new driver's
        // number is a pair nobody can act on.
        val nameless = liveDriver.copy(name = null, vehicle = null)
        val facts = TrackRideUiState(booking = booking, driver = nameless).helpFacts!!
        assertNull(facts.driverName)
        assertEquals("+93700000009", facts.driverPhone)
        assertNull(facts.plate)
    }

    @Test
    fun `the journey's ends come off the drawn map, else the booking`() {
        val bare = booking.copy(pickupStationName = null, dropoffDestinationName = null)

        val drawn = TrackRideUiState(booking = bare, journeyMap = map).helpFacts!!
        assertEquals("ایستگاه خیشکی", drawn.origin)
        assertEquals("چاریکار", drawn.destination)

        val undrawn = TrackRideUiState(booking = bare).helpFacts!!
        assertNull(undrawn.origin)
        assertNull(undrawn.destination)
    }
}
