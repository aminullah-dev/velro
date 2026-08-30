package af.velro.core.ui.component

import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Sizing
import af.velro.core.ui.theme.Spacing
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow

/**
 * The frame every screen sits in.
 *
 * Before this, nine screens were pushed onto the stack as a bare Column with
 * `statusBarsPadding()`: no title, no back control, and `BackHandler` appeared
 * nowhere in the codebase. A person deep in the driver's documents or a
 * passenger's receipt had no visible way out, and the only route back was the
 * system gesture — which many people on cheap handsets do not use, and which
 * silently abandoned an open ride request on the offers screen.
 *
 * One frame rather than nine copies, so the title, the back affordance and the
 * padding cannot drift between screens.
 *
 * @param onBack null on a root destination, which is what removes the arrow.
 *   Passing a no-op instead would draw a control that does nothing.
 * @param onBackPressed runs for the system gesture too, so a screen that must
 *   clean something up — an open request, an unsent draft — is asked either way.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VelroScreen(
    title: String,
    onBack: (() -> Unit)? = null,
    actions: @Composable () -> Unit = {},
    scrollable: Boolean = true,
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit,
) {
    val strings = LocalVelroStrings.current

    // The hardware/gesture back and the arrow do the same thing. Without this
    // a screen could clean up on one route out and not the other.
    if (onBack != null) {
        BackHandler(onBack = onBack)
    }

    Scaffold(
        modifier = modifier.fillMaxSize(),
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        title,
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.SemiBold,
                        // A long Dari title must shrink to one line rather than
                        // pushing the actions off the end of the bar.
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis,
                    )
                },
                navigationIcon = {
                    if (onBack != null) {
                        IconButton(
                            onClick = onBack,
                            modifier = Modifier.size(Sizing.touchTarget),
                        ) {
                            Icon(
                                // AutoMirrored: the arrow points the other way
                                // in Dari and Pashto, and a back arrow pointing
                                // into the text is worse than none.
                                Icons.AutoMirrored.Filled.ArrowBack,
                                contentDescription = strings["common.action.back"],
                            )
                        }
                    }
                },
                actions = { actions() },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                ),
            )
        },
    ) { insets ->
        val scroll = Modifier
            .fillMaxSize()
            .padding(insets)
            .then(if (scrollable) Modifier.verticalScroll(rememberScrollState()) else Modifier)
            .imePadding()
            .padding(horizontal = Spacing.gutter)
            .padding(bottom = Spacing.xl)

        Column(scroll) {
            content()
        }
    }
}

/** Inset values for a screen that manages its own scrolling, such as a LazyColumn. */
@Composable
fun screenContentPadding(): PaddingValues =
    PaddingValues(horizontal = Spacing.gutter, vertical = Spacing.lg)
