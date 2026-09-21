package af.velro.data.location

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationManager
import android.os.Build
import android.os.CancellationSignal
import androidx.core.content.ContextCompat
import androidx.core.location.LocationManagerCompat
import dagger.hilt.android.qualifiers.ApplicationContext
import java.util.Locale
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.coroutines.resume
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withTimeoutOrNull

/**
 * Where the handset is standing, asked politely and once.
 *
 * This exists for the geofence -- an ask or a booking summons real drivers to
 * a real station, so the server wants to know the caller is inside the service
 * area before it rings anyone -- and for "current location", which finds the
 * nearest station and lets the passenger name the place (ADR 0015). Nothing
 * here tracks: one fix per question, no listener left running, nothing stored.
 *
 * Plain [LocationManager], no Play Services. The rest of the product runs on
 * handsets that may not have Google's stack, and a network-cell fix is
 * accurate to a few hundred metres against a fence twenty kilometres wide.
 *
 * Every failure is null: permission missing, providers off, no fix inside the
 * timeout. Null goes to the server as "no location", and the server -- not the
 * app -- decides what that means. The exempt tester passes regardless; anyone
 * else is refused with a sentence in their own language. Deciding locally
 * would fork the policy into two places that would then drift.
 */
@Singleton
class LocationProvider @Inject constructor(
    @ApplicationContext private val context: Context,
) {

    data class Coordinates(
        val latitude: String,
        val longitude: String,
        /**
         * True when Android brands the fix as coming from a mock-location
         * app. Reported to the server as-is: the app neither blocks on it
         * nor hides it, because the policy for invented coordinates lives in
         * exactly one place and that place is not here.
         */
        val isMock: Boolean,
        /**
         * The radius, in metres, the phone says the fix is good to. Null when
         * it did not say. Naming a place needs a small one; the fence does not.
         */
        val accuracyMetres: Float? = null,
    )

    suspend fun current(): Coordinates? {
        if (!hasPermission()) return null
        val manager = context.getSystemService(LocationManager::class.java) ?: return null

        // A recent fix from anyone is good enough for a 20 km question --
        // walking speed cannot move a person out of the province in ten
        // minutes. Asking radios to wake up for a fresher answer wastes the
        // battery of exactly the handsets this product is built for.
        manager.allProviders
            .mapNotNull { runCatching { manager.getLastKnownLocation(it) }.getOrNull() }
            .maxByOrNull { it.time }
            ?.takeIf { System.currentTimeMillis() - it.time < RECENT_ENOUGH_MS }
            ?.let { return it.toCoordinates() }

        // GPS first, deliberately. The network provider on a handset without
        // Google's location stack -- most of this product's handsets -- claims
        // to be enabled and then never answers, and the same is true of the
        // emulator. A GPS single fix standing outdoors at a station is
        // seconds; the timeout below catches the tin-roof case.
        val provider = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
            .firstOrNull { runCatching { manager.isProviderEnabled(it) }.getOrDefault(false) }
            ?: return null

        // Bounded: a booking must not hang on a cold GPS under a tin roof.
        // Past the timeout the submission proceeds without coordinates and the
        // server says its piece.
        return withTimeoutOrNull(FIX_TIMEOUT_MS) {
            suspendCancellableCoroutine { continuation ->
                val signal = CancellationSignal()
                continuation.invokeOnCancellation { signal.cancel() }
                runCatching {
                    LocationManagerCompat.getCurrentLocation(
                        manager, provider, signal,
                        ContextCompat.getMainExecutor(context),
                    ) { location: Location? ->
                        if (continuation.isActive) continuation.resume(location?.toCoordinates())
                    }
                }.onFailure { if (continuation.isActive) continuation.resume(null) }
            }
        }
    }

    /**
     * A fix good enough to name the spot it was taken on, or null.
     *
     * The fence's [current] accepts a ten-minute-old network fix, because a
     * twenty-kilometre question does not care. "What is this place called"
     * does: a cell fix three villages wide would store the name against the
     * wrong one. So this wants fine permission, prefers GPS, accepts a
     * last-known fix only when it is both recent and tight, and waits longer
     * for a fresh one -- the passenger is standing still, looking at a card
     * that says it is finding them.
     *
     * Returns whatever it got, coarse or not; the caller reads
     * [Coordinates.accuracyMetres] and decides whether naming is offered.
     */
    suspend fun precise(): Coordinates? {
        if (!hasPermission()) return null
        val manager = context.getSystemService(LocationManager::class.java) ?: return null

        manager.allProviders
            .mapNotNull { runCatching { manager.getLastKnownLocation(it) }.getOrNull() }
            .filter { System.currentTimeMillis() - it.time < PRECISE_RECENT_MS }
            .filter { it.hasAccuracy() && it.accuracy <= PRECISE_ENOUGH_M }
            .minByOrNull { it.accuracy }
            ?.let { return it.toCoordinates() }

        val provider = listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
            .firstOrNull { runCatching { manager.isProviderEnabled(it) }.getOrDefault(false) }
            ?: return current()

        return withTimeoutOrNull(PRECISE_TIMEOUT_MS) {
            suspendCancellableCoroutine { continuation ->
                val signal = CancellationSignal()
                continuation.invokeOnCancellation { signal.cancel() }
                runCatching {
                    LocationManagerCompat.getCurrentLocation(
                        manager, provider, signal,
                        ContextCompat.getMainExecutor(context),
                    ) { location: Location? ->
                        if (continuation.isActive) continuation.resume(location?.toCoordinates())
                    }
                }.onFailure { if (continuation.isActive) continuation.resume(null) }
            }
        } ?: current()
    }

    /** Whether the precise grade is held -- Android 12 lets a person give only approximate. */
    fun hasPrecisePermission(): Boolean =
        ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED

    private fun hasPermission(): Boolean = listOf(
        Manifest.permission.ACCESS_COARSE_LOCATION,
        Manifest.permission.ACCESS_FINE_LOCATION,
    ).any {
        ContextCompat.checkSelfPermission(context, it) == PackageManager.PERMISSION_GRANTED
    }

    private fun Location.toCoordinates() = Coordinates(
        // Five decimals is about a metre -- more than the fence needs, little
        // enough not to pretend precision a cell fix does not have.
        latitude = String.format(Locale.US, "%.5f", latitude),
        longitude = String.format(Locale.US, "%.5f", longitude),
        isMock = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            isMock
        } else {
            @Suppress("DEPRECATION")
            isFromMockProvider
        },
        accuracyMetres = if (hasAccuracy()) accuracy else null,
    )

    private companion object {
        const val RECENT_ENOUGH_MS = 10L * 60 * 1000
        const val FIX_TIMEOUT_MS = 8_000L
        const val PRECISE_RECENT_MS = 2L * 60 * 1000
        const val PRECISE_ENOUGH_M = 100f
        const val PRECISE_TIMEOUT_MS = 15_000L
    }
}
