package af.velro.data.tracking

import af.velro.data.repository.RoadAlert
import kotlin.math.cos
import kotlin.math.hypot

/**
 * The next warning on the road, and how far it is.
 *
 * What the top of the full-screen trip map says on both phones in the car:
 * "Sharp bends ahead -- 2 km away", or the warning itself once they are in
 * it. Walked along the road the same way [Eta] walks it, so "2 km" is road,
 * not a straight line across a valley.
 *
 * An advisory counts only if it sits on this road and ahead of the car: the
 * server sends every advisory in the region, and a bend on the Bamyan road is
 * not news on the way to Charikar. A car off the road, or no road at all,
 * gets the zone it is standing in or nothing -- never a guess.
 */
object RoadAhead {

    data class Next(val messageKey: String, val metres: Int, val inside: Boolean)

    private const val MAX_SNAP_M = 3_000.0
    /** How far from the line an advisory may sit and still be about this road. */
    private const val ON_ROAD_SLACK_M = 300.0

    fun next(
        /** (lat, lon) pairs along the road, origin first. */
        geometry: List<Pair<Double, Double>>,
        car: Pair<Double, Double>,
        alerts: List<RoadAlert>,
    ): Next? {
        // Inside a zone: that zone, whatever the road knows.
        alerts
            .map { it to metres(car, it.latitude to it.longitude) }
            .filter { (alert, distance) -> distance <= alert.radiusM }
            .minByOrNull { it.second }
            ?.let { (alert, _) -> return Next(alert.messageKey, 0, inside = true) }

        if (geometry.size < 2) return null
        val (carIndex, carSnap) = nearest(geometry, car)
        if (carSnap > MAX_SNAP_M) return null

        val along = DoubleArray(geometry.size)
        for (i in 1 until geometry.size) along[i] = along[i - 1] + metres(geometry[i - 1], geometry[i])

        var best: Next? = null
        for (alert in alerts) {
            val (index, snap) = nearest(geometry, alert.latitude to alert.longitude)
            if (snap > alert.radiusM + ON_ROAD_SLACK_M || index <= carIndex) continue
            val ahead = (along[index] - along[carIndex]).toInt()
            if (best == null || ahead < best.metres) best = Next(alert.messageKey, ahead, inside = false)
        }
        return best
    }

    private fun nearest(points: List<Pair<Double, Double>>, target: Pair<Double, Double>): Pair<Int, Double> {
        var bestIndex = 0
        var bestDistance = Double.MAX_VALUE
        points.forEachIndexed { index, point ->
            val d = metres(point, target)
            if (d < bestDistance) {
                bestIndex = index
                bestDistance = d
            }
        }
        return bestIndex to bestDistance
    }

    private fun metres(a: Pair<Double, Double>, b: Pair<Double, Double>): Double {
        val dx = (a.second - b.second) * 111_320.0 * cos(Math.toRadians((a.first + b.first) / 2))
        val dy = (a.first - b.first) * 110_574.0
        return hypot(dx, dy)
    }
}
