package af.velro.core.ui.component

import af.velro.core.ui.theme.LocalVelroDarkTheme
import af.velro.core.ui.theme.VelroColors
import androidx.compose.foundation.Canvas
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.compositeOver
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.graphics.drawscope.scale
import androidx.compose.ui.graphics.drawscope.translate
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp

/**
 * A map, drawn rather than downloaded.
 *
 * For the places a map is wanted as a picture and not as information: the
 * sign-in card, the backdrop of home, the top of the offers screen when the
 * server could not draw the road. Streets at an angle, a park or two, and --
 * where the caller asks -- a green route between a dot and an amber pin, and a
 * few cars on the streets.
 *
 * Drawn, because a tile costs a download on a metered connection on every cold
 * open of the most-used screen, and because a map that failed to load reads as
 * a broken app on exactly the handsets that have no signal, which in Ghorband
 * is a normal morning. A Canvas costs nothing and always renders.
 *
 * It is a picture and says nothing to a screen reader: a Canvas carries no
 * semantics of its own, which is right for something that is not a fact.
 * Callers must not ask for cars where somebody could read them as live
 * vehicles -- home has none to show, and draws none.
 *
 * Mirrored in Dari and Pashto, so the route runs from the start edge to the
 * end edge the way the rest of the screen reads.
 */
@Composable
fun DrawnMap(
    modifier: Modifier = Modifier,
    route: Boolean = false,
    cars: Boolean = false,
) {
    val ink = mapInk(LocalVelroDarkTheme.current)
    val rtl = LocalLayoutDirection.current == LayoutDirection.Rtl
    Canvas(modifier) {
        scale(scaleX = if (rtl) -1f else 1f, scaleY = 1f, pivot = center) {
            drawRect(ink.ground)
            drawStreets(ink, route, cars)
        }
    }
}

/**
 * The colours of the drawn map, all from the palette.
 *
 * The ground is the palette's light neutral with a wash of its palest green
 * laid over it -- a green-grey that is plainly land without being a second
 * brand colour. Internal so ContrastTest can measure text on the glass
 * controls against the darkest thing this can put under them.
 */
internal data class MapInk(
    val ground: Color,
    val park: Color,
    val street: Color,
    val avenue: Color,
    val route: Color,
    val pin: Color,
    val car: Color,
    val carGlass: Color,
)

internal fun mapInk(dark: Boolean): MapInk = if (dark) {
    MapInk(
        ground = VelroColors.DarkGreenContainer.copy(alpha = 0.22f)
            .compositeOver(VelroColors.DarkBackground),
        park = VelroColors.DarkGreenContainer.copy(alpha = 0.55f)
            .compositeOver(VelroColors.DarkBackground),
        street = VelroColors.DarkSurfaceRaised,
        avenue = VelroColors.DarkSurfaceRaised,
        route = VelroColors.Green200,
        pin = VelroColors.Amber500,
        car = VelroColors.Green500,
        carGlass = VelroColors.Green100,
    )
} else {
    MapInk(
        ground = VelroColors.Green100.copy(alpha = 0.35f).compositeOver(VelroColors.Neutral100),
        park = VelroColors.Green100.copy(alpha = 0.85f).compositeOver(VelroColors.Neutral100),
        street = VelroColors.White,
        avenue = VelroColors.White,
        route = VelroColors.Green700,
        pin = VelroColors.Amber600,
        car = VelroColors.Green800,
        carGlass = VelroColors.Green100,
    )
}

/**
 * The street plan: a grid turned off the axis, and two avenues across it at
 * another angle -- the way a real town is a grid that the main road ignores.
 *
 * The grid is centred on the canvas and its blocks are sized from the
 * canvas's width, within bounds, so the route always lands inside the frame:
 * on the sign-in card it crosses the middle, and on a whole backdrop it is
 * the same town, simply with more of it showing round the edges.
 */
private fun DrawScope.drawStreets(ink: MapInk, route: Boolean, cars: Boolean) {
    val cellW = (size.width / CELLS_ACROSS).coerceIn(72.dp.toPx(), 112.dp.toPx())
    val cellH = minOf(cellW * 0.78f, size.height / 2.8f).coerceAtLeast(48.dp.toPx())
    val minor = 7.dp.toPx()
    val major = 13.dp.toPx()
    val reach = maxOf(size.width, size.height) * 1.6f
    // Streets run through the centre, and the route is centred on it.
    val origin = Offset(center.x, center.y - cellH * 0.5f)
    fun at(cx: Float, cy: Float) = Offset(origin.x + cx * cellW, origin.y + cy * cellH)

    rotate(degrees = -14f, pivot = center) {
        // Parks first, so the streets run over their edges.
        for ((cx, cy) in PARKS) {
            val corner = at(cx.toFloat(), cy.toFloat())
            drawRoundRect(
                color = ink.park,
                topLeft = Offset(corner.x + minor, corner.y + minor),
                size = Size(cellW - minor * 2, cellH - minor * 2),
                cornerRadius = CornerRadius(10.dp.toPx()),
            )
        }
        var x = origin.x - cellW * kotlin.math.ceil(reach / cellW)
        while (x < origin.x + reach) {
            drawLine(ink.street, Offset(x, -reach), Offset(x, reach), minor)
            x += cellW
        }
        var y = origin.y - cellH * kotlin.math.ceil(reach / cellH)
        while (y < origin.y + reach) {
            drawLine(ink.street, Offset(-reach, y), Offset(reach, y), minor)
            y += cellH
        }
    }

    // The avenues, unturned, so they cross the grid at a slant. Under the
    // route and the cars, which are on the streets, not under them.
    drawLine(
        ink.avenue,
        Offset(-size.width * 0.2f, size.height * 0.95f),
        Offset(size.width * 1.2f, size.height * 0.30f),
        major,
    )
    drawLine(
        ink.avenue,
        Offset(size.width * 0.66f, -size.height * 0.2f),
        Offset(size.width * 0.80f, size.height * 1.2f),
        major,
    )

    rotate(degrees = -14f, pivot = center) {
        if (route) {
            val stops = ROUTE.map { (cx, cy) -> at(cx, cy) }
            val path = Path().apply {
                moveTo(stops.first().x, stops.first().y)
                stops.drop(1).forEach { lineTo(it.x, it.y) }
            }
            drawPath(
                path,
                ink.route,
                style = Stroke(
                    width = 4.dp.toPx(),
                    cap = StrokeCap.Round,
                    join = StrokeJoin.Round,
                ),
            )
            drawOrigin(stops.first(), ink)
            drawPin(stops.last(), ink, upright = 14f)
        }

        if (cars) {
            for ((cx, cy, angle) in CARS) {
                drawCar(at(cx, cy), angle, ink)
            }
        }
    }
}

/** About this many blocks across the canvas. */
private const val CELLS_ACROSS = 4.6f

/** Blocks (column, row from the centre) that are parks. Few, off the route. */
private val PARKS = listOf(-2 to -1, 1 to 1, 0 to -2)

/** The route along the streets, in blocks from the centre: always on a street. */
private val ROUTE = listOf(-1.6f to 0f, 0f to 0f, 0f to 1f, 1.6f to 1f)

/** Cars on street lines, with the angle of the street they are on. */
private val CARS = listOf(
    Triple(-1f, 1f, 0f),
    Triple(1f, -0.45f, 90f),
    Triple(-2f, 0.55f, 90f),
)

/** Where the journey starts: a white dot with a ring of the route's green. */
private fun DrawScope.drawOrigin(at: Offset, ink: MapInk) {
    drawCircle(Color.White, radius = 8.dp.toPx(), center = at)
    drawCircle(ink.route, radius = 8.dp.toPx(), center = at, style = Stroke(3.dp.toPx()))
    drawCircle(ink.route, radius = 3.dp.toPx(), center = at)
}

/**
 * Where it ends: an amber pin, its point on the street.
 *
 * Counter-rotated by [upright] so it stands straight while the street plan
 * under it is turned -- a pin lying on its side reads as a fallen marker.
 */
private fun DrawScope.drawPin(at: Offset, ink: MapInk, upright: Float) {
    rotate(degrees = upright, pivot = at) {
        val r = 10.dp.toPx()
        val head = Offset(at.x, at.y - r * 2.1f)
        val path = Path().apply {
            moveTo(at.x, at.y)
            lineTo(head.x - r * 0.86f, head.y + r * 0.5f)
            lineTo(head.x + r * 0.86f, head.y + r * 0.5f)
            close()
        }
        drawPath(path, ink.pin)
        drawCircle(ink.pin, radius = r, center = head)
        drawCircle(Color.White, radius = r * 0.42f, center = head)
    }
}

/** A car seen from above, small, lying along its street. */
private fun DrawScope.drawCar(at: Offset, angle: Float, ink: MapInk) {
    val length = 18.dp.toPx()
    val width = 9.dp.toPx()
    rotate(degrees = angle, pivot = at) {
        translate(at.x - length / 2, at.y - width / 2) {
            drawRoundRect(ink.car, size = Size(length, width), cornerRadius = CornerRadius(3.dp.toPx()))
            // The windscreen and the rear window, so the car has a front.
            drawRoundRect(
                ink.carGlass,
                topLeft = Offset(length * 0.58f, width * 0.18f),
                size = Size(length * 0.16f, width * 0.64f),
                cornerRadius = CornerRadius(1.dp.toPx()),
            )
            drawRoundRect(
                ink.carGlass.copy(alpha = 0.7f),
                topLeft = Offset(length * 0.18f, width * 0.22f),
                size = Size(length * 0.12f, width * 0.56f),
                cornerRadius = CornerRadius(1.dp.toPx()),
            )
        }
    }
}

/**
 * A car seen from the side, drawn: the hero of the onboarding pages and the
 * marker that rides their progress track.
 *
 * In the brand field's green in both themes -- it is the product's emblem, not
 * a semantic colour -- with an amber headlight as the one accent. Faces the
 * end edge, so it drives the way the line it sits on is read: right in
 * English, left in Dari and Pashto.
 *
 * @param shadow the soft ellipse it stands on. Off for the small marker,
 *   where a shadow would only blur a 24dp glyph.
 */
@Composable
fun SideCar(modifier: Modifier = Modifier, shadow: Boolean = true) {
    val dark = LocalVelroDarkTheme.current
    val rtl = LocalLayoutDirection.current == LayoutDirection.Rtl
    val body = VelroColors.BrandField
    val trim = VelroColors.Green800
    val glass = if (dark) VelroColors.Green200.copy(alpha = 0.75f) else VelroColors.Green100
    val tyre = if (dark) VelroColors.Neutral700 else VelroColors.Neutral900
    val hub = VelroColors.Neutral300
    val light = VelroColors.Amber500

    Canvas(modifier) {
        // A 200 x 100 drawing, fitted to whatever box it is given.
        val unit = minOf(size.width / 200f, size.height / 100f)
        val left = (size.width - 200f * unit) / 2f
        val top = (size.height - 100f * unit) / 2f
        fun p(x: Float, y: Float) = Offset(left + x * unit, top + y * unit)

        scale(scaleX = if (rtl) -1f else 1f, scaleY = 1f, pivot = center) {
            if (shadow) {
                drawOval(
                    brush = Brush.radialGradient(
                        colors = listOf(Color.Black.copy(alpha = if (dark) 0.35f else 0.14f), Color.Transparent),
                        center = p(100f, 90f),
                        radius = 96f * unit,
                    ),
                    topLeft = p(6f, 82f),
                    size = Size(188f * unit, 16f * unit),
                )
            }

            // The cabin: a roof that slopes into the bonnet at the front.
            val cabin = Path().apply {
                moveTo(p(46f, 44f).x, p(46f, 44f).y)
                cubicTo(p(58f, 26f).x, p(58f, 26f).y, p(66f, 14f).x, p(66f, 14f).y, p(84f, 14f).x, p(84f, 14f).y)
                lineTo(p(124f, 14f).x, p(124f, 14f).y)
                cubicTo(p(138f, 14f).x, p(138f, 14f).y, p(150f, 30f).x, p(150f, 30f).y, p(162f, 44f).x, p(162f, 44f).y)
                close()
            }
            drawPath(cabin, body)

            // The body.
            drawRoundRect(
                body,
                topLeft = p(8f, 42f),
                size = Size(186f * unit, 34f * unit),
                cornerRadius = CornerRadius(16f * unit),
            )

            // Two windows, rear and front, split by the pillar.
            val rear = Path().apply {
                moveTo(p(60f, 42f).x, p(60f, 42f).y)
                cubicTo(p(66f, 30f).x, p(66f, 30f).y, p(72f, 21f).x, p(72f, 21f).y, p(86f, 21f).x, p(86f, 21f).y)
                lineTo(p(101f, 21f).x, p(101f, 21f).y)
                lineTo(p(101f, 42f).x, p(101f, 42f).y)
                close()
            }
            val front = Path().apply {
                moveTo(p(108f, 42f).x, p(108f, 42f).y)
                lineTo(p(108f, 21f).x, p(108f, 21f).y)
                lineTo(p(122f, 21f).x, p(122f, 21f).y)
                cubicTo(p(132f, 21f).x, p(132f, 21f).y, p(140f, 31f).x, p(140f, 31f).y, p(148f, 42f).x, p(148f, 42f).y)
                close()
            }
            drawPath(rear, glass)
            drawPath(front, glass)

            // The door seam and the sill, in the darker green.
            drawLine(trim, p(104.5f, 46f), p(104.5f, 68f), strokeWidth = 1.6f * unit)
            drawLine(trim, p(30f, 70f), p(172f, 70f), strokeWidth = 2f * unit, cap = StrokeCap.Round)

            // Headlight at the front, tail light at the back.
            drawRoundRect(
                light,
                topLeft = p(182f, 50f),
                size = Size(10f * unit, 7f * unit),
                cornerRadius = CornerRadius(3f * unit),
            )
            drawRoundRect(
                trim,
                topLeft = p(10f, 50f),
                size = Size(7f * unit, 7f * unit),
                cornerRadius = CornerRadius(3f * unit),
            )

            // Wheels.
            for (x in listOf(52f, 150f)) {
                drawCircle(tyre, radius = 16f * unit, center = p(x, 76f))
                drawCircle(hub, radius = 6.5f * unit, center = p(x, 76f))
            }
        }
    }
}
