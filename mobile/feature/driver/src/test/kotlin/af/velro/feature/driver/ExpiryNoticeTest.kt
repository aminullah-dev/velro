package af.velro.feature.driver

import java.time.LocalDate
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * The boundaries of the expiry warning.
 *
 * An expired licence stops a driver going online, so this line is the only
 * warning they get before being refused at the start of a shift. Showing it a
 * day early is a nuisance; showing it a day late means the first they hear of
 * it is a passenger already waiting.
 */
class ExpiryNoticeTest {

    private val today = LocalDate.of(2026, 8, 29)

    @Test
    fun `the last valid day is not expired`() {
        // A permit is good *through* its expiry date, which is the same rule
        // the server applies (expires_on >= today). If the two disagree, the
        // app tells a driver they are fine and the server refuses them.
        assertEquals(
            ExpirySeverity.SOON,
            expiryNotice("2026-08-29", today)?.severity,
        )
    }

    @Test
    fun `the day after is expired`() {
        assertEquals(
            ExpirySeverity.PAST,
            expiryNotice("2026-08-28", today)?.severity,
        )
    }

    @Test
    fun `the warning starts exactly thirty days out`() {
        assertEquals(
            ExpirySeverity.SOON,
            expiryNotice(today.plusDays(WARN_WITHIN_DAYS).toString(), today)?.severity,
        )
        assertEquals(
            ExpirySeverity.FINE,
            expiryNotice(today.plusDays(WARN_WITHIN_DAYS + 1).toString(), today)?.severity,
        )
    }

    @Test
    fun `each severity carries its own sentence`() {
        assertEquals(
            "driver.documents.expired",
            expiryNotice("2020-01-01", today)?.messageKey,
        )
        assertEquals(
            "driver.documents.expiring_soon",
            expiryNotice("2026-09-10", today)?.messageKey,
        )
        assertEquals(
            "driver.documents.valid_until",
            expiryNotice("2099-12-31", today)?.messageKey,
        )
    }

    @Test
    fun `an unparseable date says nothing rather than guessing`() {
        // Rendering a malformed expiry as "expired" would tell a driver holding
        // a valid licence to stop working.
        assertNull(expiryNotice("not-a-date", today))
        assertNull(expiryNotice("", today))
        assertNull(expiryNotice("2026-13-45", today))
    }
}
