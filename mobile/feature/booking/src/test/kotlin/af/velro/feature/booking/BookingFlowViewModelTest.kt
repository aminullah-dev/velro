package af.velro.feature.booking

import af.velro.domain.Destination
import af.velro.domain.Station
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Stepping back through the flow, and the leftover-answer bug that lived in
 * it (ADR 0009 item 3).
 *
 * `goBack()` only ever calls [BookingFlowUiState.steppedBack] -- a pure
 * function of the state, tested directly here rather than through the
 * ViewModel, which needs a live database, API client and location provider to
 * construct and has no fakes for any of them in this module.
 *
 * The bug: Back from ASK returned to DESTINATION without clearing the
 * already-chosen destination. `canSearch` -- station and destination both
 * set -- read true the moment the ask step was left, and DESTINATION used to
 * read it to enable a "Search" button that led into the pre-ADR-0004
 * fixed-price trip search: a passenger backing out of a half-finished ask to
 * reconsider the destination could tap one button and land, silently, in the
 * flow ADR 0004 replaced. The fix removed that button from
 * `BookingFlowScreen.kt`'s `DestinationList` -- it read `canSearch` nowhere
 * else -- rather than clearing the destination, because the destination
 * staying selected is what highlights it on the list and lets re-tapping it
 * go straight back into a blank ask. So `canSearch` is still expected to read
 * true here: what changed is that nothing on this screen acts on it any more.
 */
class BookingFlowViewModelTest {

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

    // A fully answered ask, so a backward step has an offer, a note and a
    // return to clear -- without these, the "cleared" assertions below would
    // pass on an already-empty form for the wrong reason.
    private fun midAsk() = BookingFlowUiState(
        step = BookingFlowUiState.Step.ASK,
        selectedStation = station,
        selectedDestination = destination,
        offeredFare = "300",
        note = "three seats, near the mosque",
        returnAfterDays = 1,
        returnFare = "250",
    )

    @Test
    fun `back from ASK returns to DESTINATION`() {
        val back = midAsk().steppedBack()
        assertEquals(BookingFlowUiState.Step.DESTINATION, back.step)
    }

    @Test
    fun `back from ASK clears the ask's own answers`() {
        // A fare typed for one destination must not silently become the
        // offer for another, and the return was left behind when it was
        // added -- so a fare typed for the way back from Kabul survived onto
        // a journey to Charikar, and so did the day it was for.
        val back = midAsk().steppedBack()
        assertEquals("", back.offeredFare)
        assertEquals("", back.note)
        assertEquals("", back.returnFare)
        assertNull(back.returnAfterDays)
    }

    @Test
    fun `back from ASK does not clear the destination that was being asked for`() {
        // Deliberate, not an oversight: DESTINATION highlights the selected
        // row from this, and tapping it again fires DestinationChosen
        // straight back into the now-blank ask. Losing it here would make
        // "reconsider the destination" indistinguishable from "start over".
        val back = midAsk().steppedBack()
        assertEquals(destination, back.selectedDestination)
        assertEquals(station, back.selectedStation)
    }

    @Test
    fun `the leftover selection alone would still satisfy canSearch`() {
        // This is the state DESTINATION's old "Search" button relied on to
        // light up after Back from ASK -- and it still holds, because
        // canSearch is also what canAsk is built from. The fix is that
        // DestinationList no longer reads canSearch at all, so this reading
        // true is inert rather than a route into the fixed-price flow. See
        // BookingFlowScreen.kt's DestinationList.
        val back = midAsk().steppedBack()
        assertTrue(back.canSearch)
    }

    @Test
    fun `an unanswered ask cannot fire despite the retained destination`() {
        // canAsk, not canSearch, is what actually gates a forward action from
        // this state now -- and an emptied fare must leave it refused.
        val back = midAsk().steppedBack()
        assertEquals(false, back.canAsk)
    }

    @Test
    fun `back from DESTINATION returns to ORIGIN_STATION`() {
        val onDestination = BookingFlowUiState(
            step = BookingFlowUiState.Step.DESTINATION,
            selectedStation = station,
        )
        assertEquals(
            BookingFlowUiState.Step.ORIGIN_STATION,
            onDestination.steppedBack().step,
        )
    }

    @Test
    fun `back from the first step goes nowhere`() {
        val first = BookingFlowUiState(step = BookingFlowUiState.Step.ORIGIN_DISTRICT)
        assertEquals(BookingFlowUiState.Step.ORIGIN_DISTRICT, first.steppedBack().step)
    }

    @Test
    fun `a refusal for a missing location is the one that offers the settings path`() {
        // The server refuses an ask with no coordinates under its own code,
        // so the screen can put the location permission beside the error.
        // The vague "outside the service area" refusal must not get that
        // button: its vagueness is deliberate, and a way to "fix" it would
        // read as a hint at how to get round the fence.
        val noFix = midAsk().copy(errorCode = GEOFENCE_LOCATION_REQUIRED)
        assertTrue(noFix.needsLocationAccess)
        val outside = midAsk().copy(errorCode = "GEOFENCE_OUTSIDE")
        assertEquals(false, outside.needsLocationAccess)
        assertEquals(false, midAsk().needsLocationAccess)
    }

    @Test
    fun `back from ASK clears the location refusal with the rest of the error`() {
        val back = midAsk().copy(errorCode = GEOFENCE_LOCATION_REQUIRED).steppedBack()
        assertNull(back.errorCode)
        assertEquals(false, back.needsLocationAccess)
    }
}
