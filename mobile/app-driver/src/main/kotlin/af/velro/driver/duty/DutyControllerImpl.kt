package af.velro.driver.duty

import af.velro.data.duty.DutyController
import android.content.Context
import dagger.Binds
import dagger.Module
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Inject
import javax.inject.Singleton

/** The app-module hand the feature's ViewModel reaches through. */
@Singleton
class DutyControllerImpl @Inject constructor(
    @ApplicationContext private val context: Context,
) : DutyController {
    override fun ensureRunning() = DriverDutyService.start(context)
    override fun stop() = DriverDutyService.stop(context)
}

@Module
@InstallIn(SingletonComponent::class)
abstract class DutyModule {
    @Binds abstract fun controller(impl: DutyControllerImpl): DutyController
}
