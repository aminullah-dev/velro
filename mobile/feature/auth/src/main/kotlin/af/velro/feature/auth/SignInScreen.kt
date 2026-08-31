package af.velro.feature.auth

import af.velro.core.ui.component.BrandHero
import af.velro.core.ui.theme.Radius
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.unit.dp
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
    /**
     * Which app is asking.
     *
     * Both apps share this screen, so the hero carried one line -- "book a
     * seat, travel with confidence" -- and showed it to drivers, who do not
     * book seats. No default on purpose: a default here is how the two apps
     * end up saying the same thing again.
     */
    taglineKey: String,
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

    SignInScreen(state = state, onEvent = viewModel::onEvent, taglineKey = taglineKey)
}

@Composable
fun SignInScreen(
    state: SignInUiState,
    onEvent: (SignInEvent) -> Unit,
    taglineKey: String = "app.tagline",
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current

    // The hero is sized from the display rather than in fixed dp, so the same
    // proportion holds on a 5" handset and a tablet.
    val heroHeight = LocalConfiguration.current.screenHeightDp.dp * 0.42f

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .imePadding(),
    ) {
        // The brand takes the top two fifths rather than a single line of it.
        //
        // This screen is six controls on a 2400px display. Centred in a plain
        // column they filled the top 45% and left a thousand pixels of empty
        // page below -- which is what made a screen with measured contrast and
        // a bundled Pashto face still read as unfinished. Giving the surplus to
        // the brand is what closes it; the alternative was stretching the form,
        // and a phone field 200px tall is not a better screen.
        BrandHero(
            title = strings["app.name"],
            subtitle = strings[taglineKey],
            minHeight = heroHeight,
        )

        // Everything below rides up over the hero's lower edge, so the card
        // reads as lying on the green rather than starting after it.
        Column(
            Modifier
                .offset(y = -Spacing.xl)
                .padding(horizontal = Spacing.gutter),
        ) {
            Card(
                shape = RoundedCornerShape(Radius.card),
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                ),
                // A hairline rather than a shadow. After dark a shadow is
                // invisible and the card is lifted by its own lightness
                // instead; the border is what keeps the edge legible in both.
                border = BorderStroke(1.dp, MaterialTheme.colorScheme.outlineVariant),
                modifier = Modifier.fillMaxWidth(),
            ) {
                Column(Modifier.padding(Spacing.lg)) {
                    // Language stays first, inside the card and above the
                    // form: a passenger who cannot read the form cannot fill
                    // it in.
                    LanguagePicker(state.locale) { onEvent(SignInEvent.LocaleChanged(it)) }

                    Spacer(Modifier.height(Spacing.xl))

                    when (state.step) {
                        SignInUiState.Step.PHONE -> PhoneStep(state, onEvent)
                        SignInUiState.Step.CODE -> CodeStep(state, onEvent)
                    }

                    if (state.errorCode != null) {
                        InlineError(state.errorCode!!, context = state.errorContext)
                    }
                }
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
            // Outside the card on purpose: it is a door out of the screen, not
            // a step in the form.
            //
            // The report door is not offered: it needs a token. The two doors that
            // need nothing still work.
            Spacer(Modifier.height(Spacing.lg))
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

            Spacer(Modifier.height(Spacing.xl))
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
        radius = Radius.pill,
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
        radius = Radius.pill,
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
