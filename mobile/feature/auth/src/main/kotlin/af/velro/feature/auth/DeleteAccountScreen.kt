package af.velro.feature.auth

import af.velro.core.ui.component.ConfirmDialog
import af.velro.core.ui.component.DestructiveAction
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.component.VelroScreen
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

/**
 * Deleting the account, from the screen that says what that means.
 *
 * Shared by both apps, like sign-in. What happens after a yes is not this
 * screen's to do: the repository clears the session, and each app's nav host
 * already sends an ended session to sign-in with the back stack cleared --
 * the same road a revoked token takes -- where the one line saying the
 * account was deleted is waiting.
 */
@Composable
fun DeleteAccountRoute(
    onBack: () -> Unit,
    /**
     * The driver app, which always explains what happens to a driver's
     * papers. The passenger app explains it too when the account is also a
     * driver's -- see [DeleteAccountViewModel.holdsDriverRecords].
     */
    isDriverApp: Boolean,
    viewModel: DeleteAccountViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val holdsDriverRecords by viewModel.holdsDriverRecords.collectAsStateWithLifecycle()

    DeleteAccountScreen(
        state = state,
        explainDriverRecords = isDriverApp || holdsDriverRecords,
        onDelete = viewModel::delete,
        onBack = onBack,
    )
}

/**
 * What goes, what stays, and the button -- in that order.
 *
 * The button is last and the explanation first because the explanation is
 * the point. "Delete account" with nothing under it asks somebody to guess
 * whether their receipts go too, and a person who guesses wrong about a
 * one-way door finds out after they have walked through it.
 */
@Composable
fun DeleteAccountScreen(
    state: AccountDeletionState,
    explainDriverRecords: Boolean,
    onDelete: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current
    var confirming by rememberSaveable { mutableStateOf(false) }
    val busy = state.isDeleting || state.deleted

    if (confirming) {
        // Asked twice, on purpose. The screen is the explanation; the dialog
        // is the moment of deciding, with the permanent part in its own words.
        ConfirmDialog(
            titleKey = "account.delete.title",
            bodyKey = "account.delete.confirm_question",
            confirmKey = "account.delete.confirm",
            destructive = true,
            onConfirm = { confirming = false; onDelete() },
            onDismiss = { confirming = false },
        )
    }

    VelroScreen(
        title = strings["account.delete.title"],
        // Held while the request is out. Leaving would not stop it -- the
        // repository finishes a deletion whatever the screen does -- but it
        // would take away the only place the answer can be read: a refusal
        // would tell nobody anything, and a yes would snatch the app to
        // sign-in from whichever screen they had wandered on to.
        onBack = { if (!busy) onBack() },
        modifier = modifier,
    ) {
        Spacer(Modifier.height(Spacing.lg))

        Section(title = strings["account.delete.gone_title"]) {
            Paragraph(strings["account.delete.gone"])
            if (explainDriverRecords) {
                Spacer(Modifier.height(Spacing.sm))
                Paragraph(strings["account.delete.gone_driver"])
            }
        }

        Spacer(Modifier.height(Spacing.md))

        Section(title = strings["account.delete.kept_title"]) {
            Paragraph(strings["account.delete.kept"])
        }

        Spacer(Modifier.height(Spacing.lg))

        Text(
            strings["account.delete.again"],
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        // Always composed, and a live region carrying its own text, so a
        // refusal is announced when it arrives: the person who tapped is
        // still on the button, and the sentence saying why nothing happened
        // lands above it.
        Box(
            Modifier
                .fillMaxWidth()
                .semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite },
        ) {
            state.errorCode?.let { code ->
                InlineError(code, context = state.errorContext)
            }
        }

        Spacer(Modifier.height(Spacing.xl))

        DestructiveAction(
            label = strings["account.delete.action"],
            onClick = { confirming = true },
            loading = busy,
        )
    }
}

@Composable
private fun Section(title: String, content: @Composable ColumnScope.() -> Unit) {
    VelroCard {
        Column(Modifier.fillMaxWidth()) {
            Text(
                title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                // Headings, so a screen reader can move between "what goes"
                // and "what stays" rather than listening to all of it twice.
                modifier = Modifier.semantics { heading() },
            )
            Spacer(Modifier.height(Spacing.xs))
            content()
        }
    }
}

@Composable
private fun Paragraph(text: String) {
    Text(text, style = MaterialTheme.typography.bodyMedium)
}
