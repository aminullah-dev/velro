package af.velro.feature.auth

import af.velro.core.i18n.Numerals
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.SecondaryAction
import af.velro.feature.safety.HelpSheet
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Sizing
import af.velro.core.ui.theme.Spacing
import af.velro.domain.Locale
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.runtime.CompositionLocalProvider
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.flow.collectLatest

/**
 * Sign in.
 *
 * Only the screen-level entry point holds a ViewModel; everything below takes
 * state and a lambda, so it can be previewed and tested without one.
 */
@Composable
fun SignInRoute(
    onSignedIn: (isDriver: Boolean, isNewUser: Boolean) -> Unit,
    viewModel: SignInViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()

    androidx.compose.runtime.LaunchedEffect(Unit) {
        viewModel.effects.collectLatest { effect ->
            when (effect) {
                is SignInEffect.SignedIn -> onSignedIn(effect.isDriver, effect.isNewUser)
            }
        }
    }

    SignInScreen(state = state, onEvent = viewModel::onEvent)
}

@Composable
fun SignInScreen(
    state: SignInUiState,
    onEvent: (SignInEvent) -> Unit,
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .imePadding()
            .padding(horizontal = Spacing.gutter, vertical = Spacing.xxl),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            strings["app.name"],
            style = MaterialTheme.typography.displaySmall,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary,
        )

        Spacer(Modifier.height(Spacing.xxxl))

        LanguagePicker(state.locale) { onEvent(SignInEvent.LocaleChanged(it)) }

        Spacer(Modifier.height(Spacing.xxl))

        when (state.step) {
            SignInUiState.Step.PHONE -> PhoneStep(state, onEvent)
            SignInUiState.Step.CODE -> CodeStep(state, onEvent)
        }

        // Get help, from the one screen a signed-out person can reach.
        //
        // Every other screen sits behind the sign-in gate: PassengerNavHost
        // sends isSignedIn=false straight to SIGN_IN with popUpTo(0), and
        // MainActivity collects that flow with initialValue=false, so a cold
        // start lands here too. Without this the emergency numbers were
        // unreachable in exactly the case they were built for -- a session
        // that expired in a valley with no data to renew it.
        //
        // The report door is not offered: it needs a token. The two doors that
        // need nothing still work.
        Spacer(Modifier.height(Spacing.xl))
        var helpOpen by remember { mutableStateOf(false) }
        SecondaryAction(
            label = strings["safety.title"],
            onClick = { helpOpen = true },
        )
        if (helpOpen) {
            HelpSheet(
                ride = null,
                canReport = false,
                onDismiss = { helpOpen = false },
            )
        }

        if (state.errorCode != null) {
            InlineError(state.errorCode!!, context = state.errorContext)
        }
    }
}

@Composable
private fun PhoneStep(state: SignInUiState, onEvent: (SignInEvent) -> Unit) {
    val strings = LocalVelroStrings.current

    Text(
        strings["auth.title.sign_in"],
        style = MaterialTheme.typography.titleLarge,
    )
    Spacer(Modifier.height(Spacing.lg))

    // A phone number is always laid out left-to-right and in Latin digits, even
    // in an RTL screen: it is a sequence to be dialled, not prose.
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        OutlinedTextField(
            value = state.phone,
            onValueChange = { onEvent(SignInEvent.PhoneChanged(Numerals.latin(it))) },
            label = { Text(strings["auth.field.phone"]) },
            placeholder = { Text("0700 123 456") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
            modifier = Modifier.fillMaxWidth().height(Sizing.fieldHeight + Spacing.sm),
        )
    }

    Spacer(Modifier.height(Spacing.xl))

    PrimaryAction(
        label = strings["auth.action.send_code"],
        onClick = { onEvent(SignInEvent.RequestCode) },
        enabled = state.canSubmitPhone,
        loading = state.isSubmitting,
    )
}

@Composable
private fun CodeStep(state: SignInUiState, onEvent: (SignInEvent) -> Unit) {
    val strings = LocalVelroStrings.current

    // Says what happened, not what the field is called -- the field carries its
    // own label, and a heading repeating it word for word left the screen
    // saying "verification code" twice with nothing telling the person a
    // message had actually gone out.
    Text(
        strings["auth.hint.code_sent"],
        style = MaterialTheme.typography.titleMedium,
        textAlign = TextAlign.Center,
    )
    Spacer(Modifier.height(Spacing.sm))
    Text(
        state.phone,
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    Spacer(Modifier.height(Spacing.lg))

    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        OutlinedTextField(
            value = state.code,
            onValueChange = { onEvent(SignInEvent.CodeChanged(Numerals.latin(it))) },
            label = { Text(strings["auth.field.code"]) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
            textStyle = MaterialTheme.typography.titleLarge.copy(textAlign = TextAlign.Center),
            modifier = Modifier.fillMaxWidth().height(Sizing.fieldHeight + Spacing.sm),
        )
    }

    Spacer(Modifier.height(Spacing.xl))

    PrimaryAction(
        label = strings["auth.action.sign_in"],
        onClick = { onEvent(SignInEvent.SubmitCode) },
        enabled = state.canSubmitCode,
        loading = state.isSubmitting,
    )

    Spacer(Modifier.height(Spacing.md))

    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically,
    ) {
        TextButton(onClick = { onEvent(SignInEvent.Back) }) {
            Text(strings["common.action.back"])
        }
        TextButton(
            onClick = { onEvent(SignInEvent.RequestCode) },
            enabled = state.canResend,
        ) {
            Text(
                if (state.canResend) {
                    strings["auth.action.resend_code"]
                } else {
                    strings["auth.action.resend_code_in", "seconds" to state.resendAfterSeconds]
                },
            )
        }
    }
}

@Composable
private fun LanguagePicker(selected: Locale, onSelect: (Locale) -> Unit) {
    // Language comes first, before anything else on the screen: a passenger who
    // cannot read the form cannot fill it in.
    Row(horizontalArrangement = Arrangement.spacedBy(Spacing.sm)) {
        for (locale in listOf(Locale.DARI, Locale.PASHTO, Locale.ENGLISH)) {
            FilterChip(
                selected = locale == selected,
                onClick = { onSelect(locale) },
                label = { Text(locale.displayName()) },
            )
        }
    }
}

private fun Locale.displayName(): String = when (this) {
    Locale.DARI -> "دری"
    Locale.PASHTO -> "پښتو"
    Locale.ENGLISH -> "English"
}
