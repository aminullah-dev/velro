package af.velro.core.ui.component

import af.velro.core.ui.theme.Radius
import af.velro.core.ui.theme.VelroColors
import af.velro.core.ui.theme.Spacing
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import android.app.Activity
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow

/**
 * The brand surface a home screen opens with.
 *
 * Both apps opened on a white bar carrying the word VELRO and two controls,
 * above a white page. Nothing was wrong with it and nothing about it was the
 * product either -- it was the default Material app bar, and it is why the
 * apps read as competent rather than finished.
 *
 * This gives the top of the screen to the brand: one green field running up
 * behind the status bar, holding the name, the controls, a greeting, and the
 * one action the screen is for. Everything below it is content on a light
 * ground. The eye lands on the green, finds the action inside it, and the
 * trips underneath read as a list rather than as the rest of an empty page.
 *
 * Green is the ground here, so everything inside owes its contrast against
 * primary rather than against white -- which is why the action slot takes a
 * white-surfaced button (see `OnBrandAction`) instead of the page's green one.
 *
 * The corners are rounded at the bottom only. A rounded top would float the
 * header away from the status bar and reintroduce the seam this removes.
 */
@Composable
fun BrandHeader(
    title: String,
    modifier: Modifier = Modifier,
    subtitle: String? = null,
    actions: @Composable RowScope.() -> Unit = {},
    content: @Composable ColumnScope.() -> Unit = {},
) {
    // The status bar sits on the green, so its icons have to be light while
    // this header is on screen -- and dark again the moment it is not, because
    // every other screen keeps a white bar. Owned here rather than at the
    // activity, so a screen cannot forget to set it or forget to put it back:
    // the header that causes the problem is the thing that fixes it.
    val view = LocalView.current
    if (!view.isInEditMode) {
        val window = (view.context as? Activity)?.window
        DisposableEffect(window) {
            val controller = window?.let { WindowCompat.getInsetsController(it, view) }
            val previous = controller?.isAppearanceLightStatusBars
            controller?.isAppearanceLightStatusBars = false
            onDispose {
                previous?.let { controller.isAppearanceLightStatusBars = it }
            }
        }
    }

    Surface(
        modifier = modifier.fillMaxWidth(),
        // The brand field, not the scheme's primary: primary inverts to pale
        // mint after dark, which turned the top of the screen into a lamp and
        // left the light status-bar icons this header forces sitting on it at
        // 1.64:1. See VelroColors.BrandField.
        color = VelroColors.BrandField,
        contentColor = VelroColors.OnBrandField,
        shape = RoundedCornerShape(
            bottomStart = Radius.xl,
            bottomEnd = Radius.xl,
        ),
    ) {
        Column(
            Modifier
                // The green runs behind the status bar; the content does not.
                .statusBarsPadding()
                .padding(horizontal = Spacing.gutter)
                .padding(top = Spacing.sm, bottom = Spacing.xl),
        ) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    title,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
                Row(verticalAlignment = Alignment.CenterVertically) { actions() }
            }

            if (subtitle != null) {
                Spacer(Modifier.height(Spacing.md))
                Text(
                    subtitle,
                    style = MaterialTheme.typography.titleMedium,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }

            content()
        }
    }
}
