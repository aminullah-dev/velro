package af.velro.data.release

import af.velro.data.api.ApiResult
import af.velro.data.api.CrashRequest
import af.velro.data.api.ResponseMapper
import af.velro.data.api.VelroApi
import android.content.Context
import android.os.Build
import dagger.hilt.android.qualifiers.ApplicationContext
import java.io.File
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

/**
 * The handset's dying words, delivered on its next breath.
 *
 * A sideloaded app has no store console and this product deliberately has no
 * third-party telemetry, so a crash in a valley two hours away either
 * reaches our own table or never existed. The mechanism is the oldest one:
 * when the process is about to die, write the stack to a file -- files
 * survive death -- and on the next launch, post it and delete it.
 *
 * Nothing personal rides along: app, version, device model, Android
 * version, trace. That is the whole envelope, and it is why the server
 * accepts it without credentials.
 */
@Singleton
class CrashTelemetry @Inject constructor(
    @ApplicationContext private val context: Context,
    private val api: VelroApi,
    private val mapper: ResponseMapper,
) {

    private val pending: File get() = File(context.filesDir, "crash-pending.json")

    /** Wraps the default handler. Call once, from Application.onCreate. */
    fun install(app: String, versionCode: Int, versionName: String) {
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            runCatching {
                pending.writeText(Json.encodeToString(CrashRequest(
                    app = app,
                    version_code = versionCode,
                    version_name = versionName,
                    device = "${Build.MANUFACTURER} ${Build.MODEL}".trim(),
                    sdk = Build.VERSION.SDK_INT,
                    stack = error.stackTraceToString().take(15_000),
                    occurred_at = Instant.now().toString(),
                )))
            }
            // The process must still die its normal death: the previous
            // handler shows the system dialog and writes logcat.
            previous?.uncaughtException(thread, error)
        }
    }

    /** Posts and deletes any stored report. Every failure just waits for
     *  the launch after this one. */
    suspend fun flush() {
        val file = pending
        if (!file.isFile) return
        val body = runCatching {
            Json.decodeFromString<CrashRequest>(file.readText())
        }.getOrElse {
            file.delete()
            return
        }
        if (mapper.call { api.reportCrash(body) } is ApiResult.Success) {
            file.delete()
        }
    }
}
