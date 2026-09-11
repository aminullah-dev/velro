package af.velro.core.ui.component

import af.velro.core.ui.theme.LocalVelroDarkTheme
import android.app.Activity
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat

/**
 * Light status-bar icons while a green brand field (BrandHeader, BrandHero)
 * is on screen, and the theme's own icons once the last one has gone.
 *
 * Counted, not saved-and-restored: each field used to remember the value it
 * found and put it back, and during a navigation transition two fields are on
 * screen at once, so the second remembered the first one's "light" and
 * restored it after both were gone -- white icons on every white screen after.
 */
@Composable
internal fun LightStatusBarIconsWhileShown() {
    val view = LocalView.current
    if (view.isInEditMode) return
    val window = (view.context as? Activity)?.window ?: return
    val darkTheme = LocalVelroDarkTheme.current
    DisposableEffect(window, darkTheme) {
        val controller = WindowCompat.getInsetsController(window, view)
        BrandFieldsOnScreen.count += 1
        controller.isAppearanceLightStatusBars = false
        onDispose {
            BrandFieldsOnScreen.count -= 1
            if (BrandFieldsOnScreen.count == 0) controller.isAppearanceLightStatusBars = !darkTheme
        }
    }
}

// Composition effects run on the main thread, so a plain counter is enough.
private object BrandFieldsOnScreen {
    var count = 0
}
