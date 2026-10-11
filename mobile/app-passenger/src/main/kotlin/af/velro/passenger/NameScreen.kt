package af.velro.passenger

import af.velro.core.ui.component.ConfirmDialog
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.InlineMessage
import af.velro.core.ui.component.PillField
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Sizing
import af.velro.core.ui.theme.Spacing
import af.velro.domain.Locale
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.flow.collectLatest

@Composable
fun NameRoute(
    onDone: () -> Unit,
    onSignOut: () -> Unit,
    viewModel: NameViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    LaunchedEffect(Unit) {
        viewModel.effects.collectLatest { effect ->
            when (effect) {
                NameEffect.Saved -> onDone()
            }
        }
    }

    NameScreen(
        state = state,
        onFirstChanged = viewModel::onFirstChanged,
        onLastChanged = viewModel::onLastChanged,
        onContinue = viewModel::submit,
        onSignOut = onSignOut,
    )
}

/**
 * "What is your name?" -- between sign-in and home, until it is answered.
 *
 * Not skippable: there is no back arrow and no "later". The system back leaves
 * the app, and the question is asked again on the next launch. The one way
 * round it is signing out, offered quietly at the foot for the person who
 * typed the wrong number and is now being asked to name an account that is
 * not theirs.
 *
 * Two fields, because a driver at a station asks for a passenger by name and
 * a first name alone is half the people waiting there. Each wants two letters
 * at least; Continue waits until both have them, and Done on the keyboard with
 * a field still short says so in words rather than doing nothing.
 *
 * The soft redesign's own language, kept minimal: the wordmark, a green
 * headline, one line on why, two pill fields and the primary pill.
 */
@Composable
fun NameScreen(
    state: NameUiState,
    onFirstChanged: (String) -> Unit,
    onLastChanged: (String) -> Unit,
    onContinue: () -> Unit,
    onSignOut: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current
    var confirming by rememberSaveable { mutableStateOf(false) }

    if (confirming) {
        // The same warning the account screen gives: signing out wipes the
        // journeys on this phone, and getting back needs a connection.
        ConfirmDialog(
            titleKey = "auth.action.sign_out",
            bodyKey = "auth.sign_out_warning",
            confirmKey = "auth.action.sign_out",
            onConfirm = { confirming = false; onSignOut() },
            onDismiss = { confirming = false },
        )
    }

    // Capital letters at the start of each word only where the script has
    // them. Dari and Pashto have no case, and a keyboard set to capitalise
    // words in them shifts to a symbol layer on some handsets.
    val capitalisation = if (strings.locale == Locale.ENGLISH) KeyboardCapitalization.Words
    else KeyboardCapitalization.None

    Surface(
        modifier = modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background,
        contentColor = MaterialTheme.colorScheme.onBackground,
    ) {
        Column(
            Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .imePadding()
                .statusBarsPadding()
                .navigationBarsPadding()
                .padding(horizontal = Spacing.gutter),
        ) {
            Spacer(Modifier.height(Spacing.lg))
            Text(
                strings["app.name"],
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary,
            )

            Spacer(Modifier.height(Spacing.xxxl))
            Text(
                strings["profile.name.title"],
                style = MaterialTheme.typography.displayLarge,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary,
            )
            Spacer(Modifier.height(Spacing.md))
            Text(
                strings["profile.name.body"],
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(Modifier.height(Spacing.xxl))
            PillField(
                value = state.first,
                onValueChange = onFirstChanged,
                label = strings["profile.field.first_name"],
                isError = state.showRequired && !PersonName.isValidPart(state.first),
                keyboardOptions = KeyboardOptions(
                    capitalization = capitalisation,
                    keyboardType = KeyboardType.Text,
                    imeAction = ImeAction.Next,
                ),
            )
            Spacer(Modifier.height(Spacing.lg))
            PillField(
                value = state.last,
                onValueChange = onLastChanged,
                label = strings["profile.field.last_name"],
                isError = state.showRequired && !PersonName.isValidPart(state.last),
                keyboardOptions = KeyboardOptions(
                    capitalization = capitalisation,
                    keyboardType = KeyboardType.Text,
                    imeAction = ImeAction.Done,
                ),
                keyboardActions = KeyboardActions(onDone = { onContinue() }),
            )

            if (state.showRequired) {
                InlineMessage("profile.error.name_required")
            }
            if (state.errorCode != null) {
                InlineError(state.errorCode, context = state.errorContext)
            }

            Spacer(Modifier.height(Spacing.xl))
            PrimaryAction(
                label = strings["common.action.continue"],
                onClick = onContinue,
                enabled = PersonName.isValid(state.first, state.last),
                loading = state.isSaving,
            )

            Spacer(Modifier.height(Spacing.md))
            TextButton(
                onClick = { confirming = true },
                enabled = !state.isSaving,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = Sizing.touchTarget),
            ) {
                Text(
                    strings["auth.action.sign_out"],
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Spacer(Modifier.height(Spacing.xl))
        }
    }
}
