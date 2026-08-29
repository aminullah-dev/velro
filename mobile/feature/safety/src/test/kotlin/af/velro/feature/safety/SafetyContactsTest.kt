package af.velro.feature.safety

import af.velro.domain.SafetyContacts
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The properties that make this feature honest rather than decorative.
 *
 * Every one of these is about what a person sees in the worst moment, so each
 * is written as the failure it prevents.
 */
class SafetyContactsTest {

    @Test
    fun `the built-in numbers are never empty`() {
        // The sheet has no loading state and no empty state on purpose: it
        // opens with these already in hand. If this list could be empty, a
        // frightened person would open Get help and find nothing to press.
        assertTrue(SafetyContacts.BUILT_IN.emergencyNumbers.isNotEmpty())
        assertEquals(listOf("119", "100"), SafetyContacts.BUILT_IN.emergencyNumbers)
    }

    @Test
    fun `the built-in copy offers no VELRO number`() {
        // support.contact_phone ships as a placeholder. A row that dials
        // nothing is worse than no row: somebody presses it and waits.
        assertNull(SafetyContacts.BUILT_IN.velroNumber)
    }

    @Test
    fun `the built-in categories match what the server accepts`() {
        // SupportTicket.__post_init__ rejects anything outside its frozenset,
        // so a client offering its own list builds a form that fails on submit.
        assertEquals(
            listOf(
                "APP_PROBLEM", "DRIVER_CONDUCT", "FARE_DISPUTE", "LOST_ITEM",
                "OTHER", "PASSENGER_CONDUCT", "SAFETY", "VEHICLE_CONDITION",
            ),
            SafetyContacts.BUILT_IN.categories.sorted(),
        )
        assertEquals(
            listOf("DRIVER_CONDUCT", "PASSENGER_CONDUCT", "SAFETY"),
            SafetyContacts.BUILT_IN.urgentCategories.sorted(),
        )
    }
}
