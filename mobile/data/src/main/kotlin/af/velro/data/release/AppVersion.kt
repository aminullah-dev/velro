package af.velro.data.release

import android.content.Context
import android.os.Build
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * The installed build's own version, read from the package manager rather
 * than a BuildConfig: feature modules have no app BuildConfig to import,
 * and the package manager answers for whichever app is hosting them.
 */
@Singleton
class AppVersion @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    val name: String by lazy {
        runCatching {
            context.packageManager.getPackageInfo(context.packageName, 0)
                .versionName ?: "0"
        }.getOrDefault("0")
    }

    val code: Int by lazy {
        runCatching {
            val info = context.packageManager.getPackageInfo(context.packageName, 0)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                info.longVersionCode.toInt()
            } else {
                @Suppress("DEPRECATION")
                info.versionCode
            }
        }.getOrDefault(1)
    }
}
