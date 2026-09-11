package af.velro.data

import af.velro.data.api.PublicPages
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The privacy page, found from the API base a build carries.
 *
 * The page is served at the root of the host, not under `/api/v1/`, so the
 * one way to get this wrong is to append rather than resolve -- and the
 * person who taps the link is then looking at a 404 where the policy should be.
 */
class PublicPagesTest {

    @Test
    fun `a development build opens the laptop's copy`() {
        assertEquals(
            "http://10.0.2.2:8000/privacy",
            PublicPages.privacyPolicyUrl("http://10.0.2.2:8000/api/v1/"),
        )
    }

    @Test
    fun `a handset on the office wifi keeps the port`() {
        assertEquals(
            "http://10.0.0.109:8000/privacy",
            PublicPages.privacyPolicyUrl("http://10.0.0.109:8000/api/v1/"),
        )
    }

    @Test
    fun `production opens production's page`() {
        assertEquals(
            "https://api.velro.linumic.com/privacy",
            PublicPages.privacyPolicyUrl("https://api.velro.linumic.com/api/v1/"),
        )
    }
}
