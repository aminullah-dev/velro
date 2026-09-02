package af.velro.driver.duty

import af.velro.core.i18n.Strings
import af.velro.data.api.ApiResult
import af.velro.data.api.TokenStore
import af.velro.data.duty.DutySignals
import af.velro.data.location.LocationProvider
import af.velro.data.repository.DriverRepository
import af.velro.data.repository.NegotiationRepository
import af.velro.data.repository.RoadAlert
import af.velro.driver.MainActivity
import af.velro.domain.Locale
import android.Manifest
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.content.pm.ServiceInfo
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Build
import android.os.IBinder
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ProcessLifecycleOwner
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject
import kotlin.math.cos
import kotlin.math.hypot
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * The driver's ears while the screen is dark.
 *
 * Every duty this product owes a working driver used to live in a ViewModel,
 * which is to say it died the moment the phone went in his pocket: no new
 * ride requests or dispatcher's offers heard, no position pings for the
 * passenger's map, no road warnings on the switchbacks. This service is
 * those duties moved somewhere the screen's fate cannot touch.
 *
 * It runs exactly while the driver is on duty -- online, or carrying a trip
 * -- under a persistent notification, which is the honest price Android
 * charges for staying alive: the driver can see the product is working, and
 * can kill it by going offline.
 *
 * When the app is on screen the service stays quiet (the UI is already
 * showing requests and banners) and only the shared [DutySignals] move;
 * when it is not, news becomes system notifications with sound, because a
 * phone in a pocket has exactly one way to say "a passenger wants you".
 */
@AndroidEntryPoint
class DriverDutyService : Service() {

    @Inject lateinit var drivers: DriverRepository
    @Inject lateinit var negotiation: NegotiationRepository
    @Inject lateinit var location: LocationProvider
    @Inject lateinit var signals: DutySignals
    @Inject lateinit var tokens: TokenStore

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var loop: Job? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startInForeground()
        if (loop?.isActive != true) loop = scope.launch { run() }
        return START_STICKY
    }

    override fun onDestroy() {
        signals.roadAlert(null)
        scope.cancel()
        super.onDestroy()
    }

    // -- the loop ---------------------------------------------------------

    private suspend fun run() {
        val strings = Strings.load(
            applicationContext,
            Locale.fromTag(tokens.locale.first()),
        )
        val announced = HashMap<String, Long>()
        var knownAsks: Set<String>? = null
        var knownOffers: Set<String>? = null
        var alerts: List<RoadAlert> = emptyList()
        var alertsForTrip: String? = null

        while (scope.isActive) {
            val assignment =
                (drivers.currentTrip() as? ApiResult.Success)?.value

            if (assignment != null) {
                val tripId = assignment.trip.id
                if (alertsForTrip != tripId) {
                    alerts = (drivers.tripMap(tripId) as? ApiResult.Success)
                        ?.value?.alerts ?: emptyList()
                    alertsForTrip = tripId
                }
                notifyDuty(strings["notif.duty.on_trip"])
                location.current()?.let { standing ->
                    drivers.pingLocation(
                        latitude = standing.latitude.toDouble(),
                        longitude = standing.longitude.toDouble(),
                    )
                    watchRoad(standing, alerts, announced, strings)
                }
                delay(TRIP_TICK_MS)
            } else {
                alertsForTrip = null
                signals.roadAlert(null)
                notifyDuty(strings["notif.duty.waiting"])
                knownAsks = watchAsks(knownAsks, strings)
                knownOffers = watchOffers(knownOffers, strings)
                delay(WAITING_TICK_MS)
            }
        }
    }

    /** New open requests become one audible notification -- pocket only. */
    private suspend fun watchAsks(known: Set<String>?, strings: Strings): Set<String> {
        val current = (negotiation.openRequests() as? ApiResult.Success)
            ?.value?.map { it.id }?.toSet()
            ?: return known ?: emptySet()
        // The first fetch is a baseline, never news: whatever was already
        // open when he came on duty is on his screen, not in his pocket.
        if (known != null && (current - known).isNotEmpty() && !appVisible()) {
            notify(
                ASK_NOTIFICATION_ID, CHANNEL_ASKS,
                strings["notif.ask.title"], strings["notif.ask.body"],
            )
            vibrateOnce()
        }
        return current
    }

    /**
     * A dispatcher's offer becomes the same audible notification -- pocket only.
     *
     * The office presses Offer and the row waits at GET driver/offers, which
     * only the home screen's ten-second poll ever read. With the screen dark
     * the offer expired unheard, and a scheduled departure went undriven
     * because the one man who could take it was told nothing. The ids kept
     * between ticks are exactly the offers open right now, so the set shrinks
     * as offers lapse or are taken and never grows past what the server holds.
     */
    private suspend fun watchOffers(known: Set<String>?, strings: Strings): Set<String> {
        val current = (drivers.offers() as? ApiResult.Success)
            ?.value?.map { it.id }?.toSet()
            ?: return known ?: emptySet()
        if (known != null && (current - known).isNotEmpty() && !appVisible()) {
            notify(
                OFFER_NOTIFICATION_ID, CHANNEL_ASKS,
                strings["notif.offer.title"], strings["notif.offer.body"],
            )
            vibrateOnce()
        }
        return current
    }

    private fun watchRoad(
        standing: LocationProvider.Coordinates,
        alerts: List<RoadAlert>,
        announced: MutableMap<String, Long>,
        strings: Strings,
    ) {
        val lat = standing.latitude.toDouble()
        val lon = standing.longitude.toDouble()
        val now = System.currentTimeMillis()
        val hit = alerts.firstOrNull { zone ->
            metres(lat, lon, zone.latitude, zone.longitude) <= zone.radiusM &&
                now - (announced["${zone.latitude}:${zone.longitude}"] ?: 0L) > COOLDOWN_MS
        }
        if (hit == null) {
            if (alerts.none { metres(lat, lon, it.latitude, it.longitude) <= it.radiusM }) {
                signals.roadAlert(null)
            }
            return
        }
        announced["${hit.latitude}:${hit.longitude}"] = now
        signals.roadAlert(hit.messageKey)
        // The buzz is the service's, on every screen and in the pocket alike:
        // the on-screen banner chimes but never vibrates, and on a ringer set
        // to vibrate the chime was the whole warning gone. Same cue as a ride
        // request, so it is felt as VELRO wanting attention.
        vibrateOnce()
        if (!appVisible()) {
            notify(
                ROAD_NOTIFICATION_ID, CHANNEL_ROAD,
                strings["notif.road.title"], strings[hit.messageKey],
            )
            // The screen's banner carries its own chime; in the pocket the
            // notification sound may be muted by profile, so the tone speaks
            // through the same stream either way.
            runCatching {
                ToneGenerator(AudioManager.STREAM_NOTIFICATION, 90).let { tone ->
                    tone.startTone(ToneGenerator.TONE_PROP_BEEP2, 400)
                }
            }
        }
    }

    private fun metres(aLat: Double, aLon: Double, bLat: Double, bLon: Double): Double {
        val dx = (aLon - bLon) * 111_320.0 * cos(Math.toRadians((aLat + bLat) / 2))
        val dy = (aLat - bLat) * 110_574.0
        return hypot(dx, dy)
    }

    private fun appVisible(): Boolean =
        ProcessLifecycleOwner.get().lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)

    /**
     * The vibration half of the home screen's `ringOnce`, for the service.
     *
     * The sound half is the channel's own -- a notification on CHANNEL_ASKS
     * or CHANNEL_ROAD already plays the notification sound, and ringing the
     * ringtone on top of it would be the same sound twice. The buzz is what
     * a silenced ringer leaves as the only cue, and what the road banner on
     * screen does not give at all.
     */
    private fun vibrateOnce() {
        runCatching {
            val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                (getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager)
                    .defaultVibrator
            } else {
                @Suppress("DEPRECATION")
                getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                vibrator.vibrate(
                    VibrationEffect.createOneShot(VIBRATE_MS, VibrationEffect.DEFAULT_AMPLITUDE)
                )
            } else {
                @Suppress("DEPRECATION")
                vibrator.vibrate(VIBRATE_MS)
            }
        }
    }

    // -- notifications ----------------------------------------------------

    private fun startInForeground() {
        channels()
        val type = if (hasLocationPermission()) {
            ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION
        } else {
            // Without the permission the service still listens for requests;
            // it simply cannot ping. Android demands the type match reality.
            ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
        }
        ServiceCompat.startForeground(
            this, DUTY_NOTIFICATION_ID, dutyNotification(""), type,
        )
    }

    private fun hasLocationPermission(): Boolean = listOf(
        Manifest.permission.ACCESS_FINE_LOCATION,
        Manifest.permission.ACCESS_COARSE_LOCATION,
    ).any {
        ContextCompat.checkSelfPermission(this, it) == PackageManager.PERMISSION_GRANTED
    }

    private fun notifyDuty(text: String) {
        manager().notify(DUTY_NOTIFICATION_ID, dutyNotification(text))
    }

    private fun dutyNotification(text: String): Notification =
        NotificationCompat.Builder(this, CHANNEL_DUTY)
            .setSmallIcon(android.R.drawable.ic_menu_mylocation)
            .setContentTitle("ولرو")
            .setContentText(text)
            .setOngoing(true)
            .setSilent(true)
            .setContentIntent(openApp())
            .build()

    private fun notify(id: Int, channel: String, title: String, body: String) {
        runCatching {
            manager().notify(
                id,
                NotificationCompat.Builder(this, channel)
                    .setSmallIcon(android.R.drawable.ic_dialog_info)
                    .setContentTitle(title)
                    .setContentText(body)
                    .setStyle(NotificationCompat.BigTextStyle().bigText(body))
                    .setPriority(NotificationCompat.PRIORITY_HIGH)
                    .setAutoCancel(true)
                    .setContentIntent(openApp())
                    .build(),
            )
        }
    }

    private fun openApp(): PendingIntent = PendingIntent.getActivity(
        this, 0,
        Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )

    private fun channels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = manager()
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_DUTY, "در حال کار", NotificationManager.IMPORTANCE_LOW)
        )
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ASKS, "درخواست‌های سفر", NotificationManager.IMPORTANCE_HIGH)
        )
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ROAD, "هشدارهای جاده", NotificationManager.IMPORTANCE_HIGH)
                .apply {
                    // A hazard must be felt as well as heard. Android keeps a
                    // channel's first settings, so on a phone that already
                    // has this channel the buzz comes from vibrateOnce() and
                    // this only reaches fresh installs.
                    enableVibration(true)
                    vibrationPattern = longArrayOf(0L, VIBRATE_MS)
                }
        )
    }

    private fun manager(): NotificationManager =
        getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

    companion object {
        private const val CHANNEL_DUTY = "velro.duty"
        private const val CHANNEL_ASKS = "velro.asks"
        private const val CHANNEL_ROAD = "velro.road"
        private const val DUTY_NOTIFICATION_ID = 100
        private const val ASK_NOTIFICATION_ID = 101
        private const val ROAD_NOTIFICATION_ID = 102
        private const val OFFER_NOTIFICATION_ID = 103
        private const val TRIP_TICK_MS = 30_000L
        private const val WAITING_TICK_MS = 45_000L
        private const val COOLDOWN_MS = 10L * 60 * 1000
        private const val VIBRATE_MS = 400L

        fun start(context: Context) {
            ContextCompat.startForegroundService(
                context, Intent(context, DriverDutyService::class.java),
            )
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, DriverDutyService::class.java))
        }
    }
}
