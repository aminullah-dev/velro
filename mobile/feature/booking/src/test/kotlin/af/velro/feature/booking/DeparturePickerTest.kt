package af.velro.feature.booking

import af.velro.domain.Destination
import af.velro.domain.Station
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The hours a passenger is offered, and the hour actually held.
 *
 * These drifted apart. The day chips carry the existing hour through, and the
 * hours on offer change with the day: at six in the evening, tapping "today"
 * left the six-o'clock default selected while the row showed 19:00 and 20:00.
 * No chip looked chosen, and "ask for a car" sent this morning -- refused by
 * the server every time, with a message about a departure in the past that the
 * passenger had never picked. In the evening, "today" simply did not work.
 *
 * The clock is on the state so this can be asked at 18:00 without waiting
 * until 18:00.
 */
class DeparturePickerTest {

    // A journey already chosen, so `canAsk` turns on the hour rules rather
    // than on a half-filled form -- without these two, every canAsk assertion
    // below would be true for the wrong reason.
    private val station = Station(
        id = "01a05400-0000-7000-8000-00000000000c",
        code = "GRB-SYG-001-S1",
        name = "ایستگاه خیشکی",
        villageId = "01a05400-0000-7000-8000-00000000000e",
        districtId = "01a05400-0000-7000-8000-00000000000f",
    )
    private val destination = Destination(
        id = "01a05400-0000-7000-8000-00000000000d",
        code = "CHK",
        name = "چاریکار",
        kind = "EXTERNAL",
    )

    private fun ask(hour: Int) = BookingFlowUiState(
        step = BookingFlowUiState.Step.ASK,
        selectedStation = station,
        selectedDestination = destination,
        offeredFare = "300",
        nowHour = hour,
    )

    @Test
    fun `an evening 'today' moves the hour into the hours on offer`() {
        val evening = ask(hour = 18).copy(departureDay = 0).withHoursInRange()
        assertEquals(listOf(19, 20), evening.departureHours)
        assertTrue(
            "the held hour ${evening.departureHour} is not one of the offered hours",
            evening.departureHour in evening.departureHours,
        )
    }

    @Test
    fun `a morning 'today' leaves an already-valid hour alone`() {
        val morning = ask(hour = 5).copy(departureDay = 0).withHoursInRange()
        assertEquals(6, morning.departureHour)
    }

    @Test
    fun `tomorrow always offers the whole day whatever time it is now`() {
        val late = ask(hour = 23).copy(departureDay = 1).withHoursInRange()
        assertEquals(4, late.departureHours.first())
        assertEquals(6, late.departureHour)
    }

    @Test
    fun `a same-day return is moved after the outbound`() {
        // Departure 19:00, return "same day": the only hour left is 20:00, and
        // the 14:00 default would be a return before the outbound -- refused
        // by the server for a different reason than the one above.
        val s = ask(hour = 18)
            .copy(departureDay = 0, departureHour = 19, returnAfterDays = 0)
            .withHoursInRange()
        assertTrue(
            "return ${s.returnHour} must be one of ${s.returnHours}",
            s.returnHour in s.returnHours,
        )
        assertTrue("the return must leave after the outbound", s.returnHour > s.departureHour)
    }

    @Test
    fun `a later-day return keeps the ordinary afternoon default`() {
        val s = ask(hour = 8)
            .copy(departureDay = 1, departureHour = 6, returnAfterDays = 1)
            .withHoursInRange()
        assertEquals(14, s.returnHour)
    }

    @Test
    fun `a day with no hours left cannot be asked for`() {
        // Past the last departure, "today" offers nothing. The picker says so;
        // this is what stops the button sending it anyway.
        val spent = ask(hour = 22).copy(departureDay = 0).withHoursInRange()
        assertTrue("no hours should remain at 22:00", spent.departureHours.isEmpty())
        assertFalse("the ask button must be refused on a spent day", spent.canAsk)
    }

    @Test
    fun `asking for a car right now is unaffected by any of this`() {
        // departureDay null means "now": no hours, no clamping, and the
        // request carries no departure at all.
        val now = ask(hour = 22).copy(departureDay = null).withHoursInRange()
        assertTrue("the common case must stay askable at any hour", now.canAsk)
        assertEquals(null, now.requestedFor())
    }
}
