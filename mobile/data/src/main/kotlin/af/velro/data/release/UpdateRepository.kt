package af.velro.data.release

import af.velro.data.BuildConfig
import af.velro.data.api.ApiResult
import af.velro.data.api.ResponseMapper
import af.velro.data.api.VelroApi
import javax.inject.Inject
import javax.inject.Singleton

/**
 * How a sideloaded app learns it is old.
 *
 * There is no store to whisper updates; the backend's own /app/version is
 * the only voice. Asked once per launch, fire-and-forget: a failure means
 * no banner, never an error -- being unable to check for updates is not a
 * problem worth a passenger's attention.
 *
 * The same question carries an answer back the other way: which app and
 * which build asked. Without a store there is no other count of the versions
 * still in the field, and no way to know when the last phone on a broken
 * build has finally moved on. It names the build and nothing about the
 * person holding it.
 */
@Singleton
class UpdateRepository @Inject constructor(
    private val api: VelroApi,
    private val mapper: ResponseMapper,
) {

    /** A download URL, only when the server holds something newer. */
    suspend fun availableUpdate(app: String, currentCode: Int, currentName: String): String? {
        // A name outside the two apps is a caller's slip, not a third app.
        // Filing its version under either would put a wrong row in the count;
        // sending nothing loses one row, which is the cheaper mistake. The
        // update check itself still runs either way.
        val known = app in KNOWN_APPS
        val answer = mapper.call {
            api.appVersion(
                app = app.takeIf { known },
                platform = PLATFORM.takeIf { known },
                versionCode = currentCode.takeIf { known },
                versionName = currentName.takeIf { known },
            )
        }
        val release = (answer as? ApiResult.Success)?.value ?: return null
        if (release.available != true) return null
        val channel = when (app) {
            "driver" -> release.driver
            else -> release.passenger
        } ?: return null
        if (channel.version_code <= currentCode) return null
        return releaseUrl(BuildConfig.API_BASE_URL, channel.apk)
    }

    companion object {
        /** The names the callers already use for crash reports; lowercase on the wire. */
        private val KNOWN_APPS = setOf("passenger", "driver")

        /** This module only ever ships inside an Android app. */
        private const val PLATFORM = "android"

        /**
         * The APK path is server-relative ("/app/velro-passenger.apk"); the
         * base the app knows ends in "api/v1/". Pure so a test can hold the
         * seam still.
         */
        fun releaseUrl(apiBase: String, apkPath: String): String =
            apiBase.removeSuffix("api/v1/").removeSuffix("/") + apkPath
    }
}
