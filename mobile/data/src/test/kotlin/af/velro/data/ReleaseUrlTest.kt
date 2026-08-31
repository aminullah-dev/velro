package af.velro.data

import af.velro.data.release.UpdateRepository
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * The seam between the API base a build carries and the server-relative APK
 * path the release manifest publishes. One wrong slash here and every
 * update tap opens a 404 in a bazaar full of testers.
 */
class ReleaseUrlTest {

    @Test
    fun `the api prefix is peeled off and the path grafted on`() {
        assertEquals(
            "http://10.0.2.2:8000/app/velro-passenger.apk",
            UpdateRepository.releaseUrl(
                "http://10.0.2.2:8000/api/v1/", "/app/velro-passenger.apk",
            ),
        )
    }

    @Test
    fun `a production host with no port works the same way`() {
        assertEquals(
            "https://api.velro.linumic.com/app/velro-driver.apk",
            UpdateRepository.releaseUrl(
                "https://api.velro.linumic.com/api/v1/", "/app/velro-driver.apk",
            ),
        )
    }
}
