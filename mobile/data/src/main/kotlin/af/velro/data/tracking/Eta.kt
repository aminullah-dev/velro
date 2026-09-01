package af.velro.data.tracking

import kotlin.math.cos
import kotlin.math.hypot

/**
 * "Arriving in about N minutes", computed honestly or not at all.
 *
 * The distance is walked along the actual road polyline between the point
 * nearest the car and the point nearest where the car is headed; the speed
 * is the routing engine's own average for that road. No traffic feed, no
 * machine learning -- a valley with one road does not need them, and a
 * number this screen cannot defend is a number it must not show: a car
 * more than [MAX_SNAP_M] off the line gets null, not a guess.
 */
object Eta {

    private const val MAX_SNAP_M = 3_000.0

    fun minutes(
        /** (lat, lon) pairs along the road, origin first. */
        geometry: List<Pair<Double, Double>>,
        car: Pair<Double, Double>,
        target: Pair<Double, Double>,
        avgSpeedKmh: Double?,
    ): Int? {
        if (geometry.size < 2 || avgSpeedKmh == null || avgSpeedKmh <= 0.0) return null
        val (carIndex, carSnap) = nearest(geometry, car)
        val (targetIndex, targetSnap) = nearest(geometry, target)
        if (carSnap > MAX_SNAP_M || targetSnap > MAX_SNAP_M) return null
        val from = minOf(carIndex, targetIndex)
        val until = maxOf(carIndex, targetIndex)
        var metres = 0.0
        for (i in from until until) {
            metres += metresBetween(geometry[i], geometry[i + 1])
        }
        return ((metres / 1000.0) / avgSpeedKmh * 60.0).toInt()
    }

    private fun nearest(
        points: List<Pair<Double, Double>>,
        target: Pair<Double, Double>,
    ): Pair<Int, Double> {
        var bestIndex = 0
        var bestDistance = Double.MAX_VALUE
        points.forEachIndexed { index, point ->
            val d = metresBetween(point, target)
            if (d < bestDistance) {
                bestIndex = index
                bestDistance = d
            }
        }
        return bestIndex to bestDistance
    }

    private fun metresBetween(a: Pair<Double, Double>, b: Pair<Double, Double>): Double {
        val dx = (a.second - b.second) * 111_320.0 *
            cos(Math.toRadians((a.first + b.first) / 2))
        val dy = (a.first - b.first) * 110_574.0
        return hypot(dx, dy)
    }
}
