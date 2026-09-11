package af.velro.data

import af.velro.data.repository.RoadAlert
import af.velro.data.tracking.RoadAhead
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The warning at the top of the trip map, on a road whose length is known by
 * construction: a straight east-west line at latitude 35, 0.01° of longitude
 * (about 912 m) between points, driven west to east.
 */
class RoadAheadTest {

    private val road = (0..20).map { 35.0 to 68.0 + it * 0.01 }

    private fun alert(lon: Double, key: String, lat: Double = 35.0, radius: Int = 300) =
        RoadAlert(lat, lon, radius, "curve", key)

    @Test
    fun `the nearest warning ahead, measured along the road`() {
        val next = RoadAhead.next(
            road, car = 35.0 to 68.02,
            alerts = listOf(alert(68.10, "road.alert.caution"), alert(68.05, "road.alert.curve")),
        )!!
        assertEquals("road.alert.curve", next.messageKey)
        assertTrue("~2.7 km, got ${next.metres}", next.metres in 2_600..2_900)
        assertEquals(false, next.inside)
    }

    @Test
    fun `a warning already passed is not news`() {
        val next = RoadAhead.next(road, 35.0 to 68.12, listOf(alert(68.05, "road.alert.curve")))
        assertNull(next)
    }

    @Test
    fun `a warning on another road is not about this one`() {
        // Five kilometres north of the line: a different valley's bend.
        val next = RoadAhead.next(road, 35.0 to 68.02, listOf(alert(68.08, "road.alert.curve", lat = 35.045)))
        assertNull(next)
    }

    @Test
    fun `inside a zone, the zone itself`() {
        val next = RoadAhead.next(road, 35.0 to 68.05, listOf(alert(68.051, "road.alert.bazaar", radius = 400)))!!
        assertEquals("road.alert.bazaar", next.messageKey)
        assertEquals(0, next.metres)
        assertTrue(next.inside)
    }

    @Test
    fun `a car far off the road gets no guess`() {
        assertNull(RoadAhead.next(road, 35.5 to 69.5, listOf(alert(68.10, "road.alert.curve"))))
    }
}
