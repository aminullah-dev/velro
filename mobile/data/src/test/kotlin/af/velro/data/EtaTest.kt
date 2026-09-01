package af.velro.data

import af.velro.data.tracking.Eta
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * The arithmetic behind "arriving in about N minutes", pinned on a road
 * whose length is known by construction: a straight east-west line at
 * latitude 35, where 0.01 degrees of longitude is about 912 metres.
 */
class EtaTest {

    // 21 points, 0.01° apart: ~18.2 km end to end.
    private val road = (0..20).map { 35.0 to (68.0 + it * 0.01) }

    @Test
    fun `car halfway, heading to the end, at 60 kmh`() {
        val eta = Eta.minutes(road, car = 35.0 to 68.10, target = 35.0 to 68.20, avgSpeedKmh = 60.0)
        // ~9.1 km at 60 km/h is ~9 minutes.
        assertEquals(9, eta)
    }

    @Test
    fun `direction does not matter -- the road is walked between the two`() {
        val forward = Eta.minutes(road, 35.0 to 68.02, 35.0 to 68.18, 60.0)
        val backward = Eta.minutes(road, 35.0 to 68.18, 35.0 to 68.02, 60.0)
        assertEquals(forward, backward)
    }

    @Test
    fun `a car far off the road earns null, not a guess`() {
        assertNull(Eta.minutes(road, car = 35.2 to 68.10, target = 35.0 to 68.20, avgSpeedKmh = 60.0))
    }

    @Test
    fun `no speed, no answer`() {
        assertNull(Eta.minutes(road, 35.0 to 68.10, 35.0 to 68.20, null))
    }
}
