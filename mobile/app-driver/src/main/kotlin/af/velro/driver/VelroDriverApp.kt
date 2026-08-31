package af.velro.driver

import af.velro.data.release.AppVersion
import af.velro.data.release.CrashTelemetry
import af.velro.data.sync.SyncWorker
import android.app.Application
import androidx.hilt.work.HiltWorkerFactory
import androidx.work.Configuration
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject
import kotlinx.coroutines.launch

@HiltAndroidApp
class VelroDriverApp : Application(), Configuration.Provider {

    @Inject lateinit var workerFactory: HiltWorkerFactory
    @Inject lateinit var crashTelemetry: CrashTelemetry
    @Inject lateinit var appVersion: AppVersion

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder().setWorkerFactory(workerFactory).build()

    override fun onCreate() {
        super.onCreate()
        // Starts the offline queue draining as soon as there is a connection,
        // whether or not the app is open.
        SyncWorker.schedule(this)
        // If the previous run died screaming, its stack is on disk; send it
        // and stand ready to catch this run's own last words.
        crashTelemetry.install(
            app = "driver",
            versionCode = appVersion.code,
            versionName = appVersion.name,
        )
        kotlinx.coroutines.CoroutineScope(
            kotlinx.coroutines.SupervisorJob() + kotlinx.coroutines.Dispatchers.IO
        ).launch { crashTelemetry.flush() }
    }
}
