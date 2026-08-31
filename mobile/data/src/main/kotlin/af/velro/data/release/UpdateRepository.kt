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
 */
@Singleton
class UpdateRepository @Inject constructor(
    private val api: VelroApi,
    private val mapper: ResponseMapper,
) {

    /** A download URL, only when the server holds something newer. */
    suspend fun availableUpdate(app: String, currentCode: Int): String? {
        val answer = mapper.call { api.appVersion() }
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
        /**
         * The APK path is server-relative ("/app/velro-passenger.apk"); the
         * base the app knows ends in "api/v1/". Pure so a test can hold the
         * seam still.
         */
        fun releaseUrl(apiBase: String, apkPath: String): String =
            apiBase.removeSuffix("api/v1/").removeSuffix("/") + apkPath
    }
}
