package af.velro.feature.driver

import af.velro.data.repository.TripMapData
import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import af.velro.core.ui.theme.Radius
import androidx.compose.foundation.shape.RoundedCornerShape
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.geometry.LatLngBounds
import org.maplibre.android.location.LocationComponentActivationOptions
import org.maplibre.android.location.modes.CameraMode
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.PropertyFactory.circleColor
import org.maplibre.android.style.layers.PropertyFactory.circleRadius
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeColor
import org.maplibre.android.style.layers.PropertyFactory.circleStrokeWidth
import org.maplibre.android.style.layers.PropertyFactory.lineCap
import org.maplibre.android.style.layers.PropertyFactory.lineColor
import org.maplibre.android.style.layers.PropertyFactory.lineJoin
import org.maplibre.android.style.layers.PropertyFactory.lineWidth
import org.maplibre.android.style.sources.GeoJsonSource
import org.maplibre.geojson.Feature
import org.maplibre.geojson.FeatureCollection
import org.maplibre.geojson.LineString
import org.maplibre.geojson.Point

/**
 * The journey, drawn.
 *
 * The base map is the product's own: an OpenStreetMap extract served by the
 * VELRO backend, so there is no third-party key, no quota and no Play
 * Services -- the same ethos as the rest of the app, applied to tiles. What
 * this adds over the text card is orientation: the valley, the road, the
 * stations as dots, the journey as a line, and the driver's own position
 * moving along it.
 *
 * Everything here fails soft. No permission means no blue dot, not a prompt
 * (the booking flow already asks at the moment that matters); no tiles means
 * a plain background with the line still drawn; no line means dots on a
 * map. The card never raises an error -- a map is a bonus, and a driver
 * mid-journey has no use for its apologies.
 */
@Composable
fun TripMap(data: TripMapData, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    // Must run before the first MapView is constructed, once per process.
    remember { MapLibre.getInstance(context.applicationContext) }

    val mapView = remember { MapView(context) }
    val lifecycle = LocalLifecycleOwner.current.lifecycle

    DisposableEffect(lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_START -> mapView.onStart()
                Lifecycle.Event.ON_RESUME -> mapView.onResume()
                Lifecycle.Event.ON_PAUSE -> mapView.onPause()
                Lifecycle.Event.ON_STOP -> mapView.onStop()
                else -> Unit
            }
        }
        mapView.onCreate(null)
        lifecycle.addObserver(observer)
        onDispose {
            lifecycle.removeObserver(observer)
            mapView.onDestroy()
        }
    }

    AndroidView(
        factory = { mapView },
        modifier = modifier
            .fillMaxWidth()
            .height(220.dp)
            .clip(RoundedCornerShape(Radius.card)),
        update = { view ->
            view.getMapAsync { map -> map.render(context, data) }
        },
    )
}

private fun MapLibreMap.render(context: Context, data: TripMapData) {
    // A card, not a navigator: no rotation, no tilt, pinch and pan only.
    uiSettings.isRotateGesturesEnabled = false
    uiSettings.isTiltGesturesEnabled = false
    // The ODbL price of the data is its credit line; it stays.
    uiSettings.isAttributionEnabled = true
    uiSettings.isLogoEnabled = false

    setStyle(Style.Builder().fromUri(data.styleUrl)) { style ->
        val stations = FeatureCollection.fromFeatures(
            data.stations.map {
                Feature.fromGeometry(Point.fromLngLat(it.longitude, it.latitude))
            }
        )
        style.addSource(GeoJsonSource("velro-stations", stations))
        style.addLayer(
            CircleLayer("velro-station-dots", "velro-stations").withProperties(
                circleRadius(3.5f),
                circleColor("#7a7264"),
                circleStrokeColor("#ffffff"),
                circleStrokeWidth(1.2f),
            )
        )

        data.geometry?.let { line ->
            val path = LineString.fromLngLats(
                line.map { (lat, lon) -> Point.fromLngLat(lon, lat) }
            )
            style.addSource(GeoJsonSource("velro-journey", path))
            style.addLayer(
                LineLayer("velro-journey-line", "velro-journey").withProperties(
                    lineColor("#1c1b16"),
                    lineWidth(3.5f),
                    lineCap("round"),
                    lineJoin("round"),
                )
            )
        }

        val ends = FeatureCollection.fromFeatures(
            listOfNotNull(data.origin, data.destination).map {
                Feature.fromGeometry(Point.fromLngLat(it.longitude, it.latitude))
            }
        )
        style.addSource(GeoJsonSource("velro-ends", ends))
        style.addLayer(
            CircleLayer("velro-end-dots", "velro-ends").withProperties(
                circleRadius(6f),
                circleColor("#f5c400"),
                circleStrokeColor("#1c1b16"),
                circleStrokeWidth(2f),
            )
        )

        enableOwnPosition(context, style)
        frame(data)
    }
}

/** The blue dot, only if the permission already exists. Never asks. */
private fun MapLibreMap.enableOwnPosition(context: Context, style: Style) {
    val granted = listOf(
        Manifest.permission.ACCESS_FINE_LOCATION,
        Manifest.permission.ACCESS_COARSE_LOCATION,
    ).any {
        ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED
    }
    if (!granted) return
    runCatching {
        locationComponent.activateLocationComponent(
            LocationComponentActivationOptions.builder(context, style).build()
        )
        @Suppress("MissingPermission")
        locationComponent.isLocationComponentEnabled = true
        locationComponent.cameraMode = CameraMode.NONE
    }
}

/** Fit the journey; fall back to whatever points exist; else the region. */
private fun MapLibreMap.frame(data: TripMapData) {
    val points = buildList {
        data.geometry?.let { line ->
            // Enough of the line to bound it; every vertex would be waste.
            val step = maxOf(1, line.size / 50)
            for (i in line.indices step step) add(LatLng(line[i].first, line[i].second))
            add(LatLng(line.last().first, line.last().second))
        }
        data.origin?.let { add(LatLng(it.latitude, it.longitude)) }
        data.destination?.let { add(LatLng(it.latitude, it.longitude)) }
        if (isEmpty()) data.stations.forEach { add(LatLng(it.latitude, it.longitude)) }
    }
    when {
        points.size >= 2 -> runCatching {
            moveCamera(
                CameraUpdateFactory.newLatLngBounds(
                    LatLngBounds.Builder().includes(points).build(), 48,
                )
            )
        }
        points.size == 1 ->
            moveCamera(CameraUpdateFactory.newLatLngZoom(points.first(), 11.0))
        else ->
            // The middle of the product's world, roughly سیاه‌گرد.
            moveCamera(CameraUpdateFactory.newLatLngZoom(LatLng(34.95, 68.8), 8.0))
    }
}
