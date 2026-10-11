package af.velro.feature.auth

import af.velro.core.i18n.Numerals
import af.velro.core.ui.component.ChoiceChip
import af.velro.core.ui.component.DrawnMap
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.PillField
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.component.softShadow
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Radius
import af.velro.core.ui.theme.Sizing
import af.velro.core.ui.theme.Spacing
import af.velro.data.api.PublicPages
import af.velro.domain.Locale
import af.velro.feature.safety.HelpSheet
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Phone
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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
    val context = LocalContext.current

    // The picture is sized from the display rather than in fixed dp, so the
    // same proportion holds on a 5" handset and a tablet -- bounded both
    // ways, so a small phone keeps room for the form and a tablet does not
    // get a map the size of a poster.
    val mapHeight = (LocalConfiguration.current.screenHeightDp.dp * 0.24f)
        .coerceIn(MAP_MIN, MAP_MAX)

    // The page's own ground and foreground, set here: this screen has no
    // Scaffold to paint it, and after dark the window behind it is not the
    // theme -- nor is the black that uncoloured text falls back to.
    Surface(
        modifier = modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.background,
        contentColor = MaterialTheme.colorScheme.onBackground,
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .imePadding()
                .statusBarsPadding()
                .navigationBarsPadding()
                .padding(horizontal = Spacing.gutter),
        ) {
            Spacer(Modifier.height(Spacing.lg))

            // The brand, small, where a name belongs: at the top, once.
            //
            // This screen used to give its top two fifths to a green field with
            // the name at display size. The soft redesign hands that space to a
            // picture of what the product is instead -- a map with a route and
            // cars on it -- and keeps the name as a wordmark above it.
            Text(
                strings["app.name"],
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.primary,
            )
            Text(
                // Which app is asking: drivers do not book seats, so they get
                // their own line. See SignInRoute.
                strings[taglineKey],
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(Modifier.height(Spacing.lg))

            // Decoration, and nothing else: no tile is fetched for it, and a
            // screen reader passes over it, because nothing on it is true of any
            // real street or car.
            val cardShape = RoundedCornerShape(Radius.surface)
            Box(
                Modifier
                    .fillMaxWidth()
                    .height(mapHeight)
                    .softShadow(cardShape)
                    .clip(cardShape),
            ) {
                DrawnMap(Modifier.fillMaxSize(), route = true, cars = true)
            }

            Spacer(Modifier.height(Spacing.xl))

            if (state.accountDeleted) {
                AccountDeletedNotice()
                Spacer(Modifier.height(Spacing.lg))
            }

            // Language stays first in the form: a passenger who cannot read the
            // form cannot fill it in.
            LanguagePicker(state.locale) { onEvent(SignInEvent.LocaleChanged(it)) }

            Spacer(Modifier.height(Spacing.xl))

            when (state.step) {
                SignInUiState.Step.PHONE -> PhoneStep(state, onEvent)
                SignInUiState.Step.CODE -> CodeStep(state, onEvent)
            }

            if (state.errorCode != null) {
                InlineError(state.errorCode!!, context = state.errorContext)
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
            // Below the form on purpose: it is a door out of the screen, not a
            // step in it.
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

            // What VELRO will keep, readable before the number is handed over --
            // the one moment a person is deciding whether to give it. The page the
            // server publishes, in the browser, like the account screens' link.
            Spacer(Modifier.height(Spacing.sm))
            TextButton(
                onClick = {
                    // A handset with no browser is rare, not impossible, and a tap
                    // that throws takes the whole app down with it.
                    runCatching {
                        context.startActivity(
                            Intent(Intent.ACTION_VIEW, Uri.parse(PublicPages.privacyPolicyUrl))
                        )
                    }
                },
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = Sizing.touchTarget),
            ) {
                Text(
                    strings["account.privacy"],
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            Spacer(Modifier.height(Spacing.xl))
        }
    }
}

private val MAP_MIN = 160.dp
private val MAP_MAX = 240.dp

@Composable
private fun PhoneStep(state: SignInUiState, onEvent: (SignInEvent) -> Unit) {
    val strings = LocalVelroStrings.current

    Text(
        strings["auth.title.sign_in"],
        style = MaterialTheme.typography.headlineSmall,
        fontWeight = FontWeight.Bold,
    )
    Spacer(Modifier.height(Spacing.lg))

    // Where the code should arrive, chosen by the person who knows.
    //
    // Not a guess from the number: whether somebody uses Telegram is not
    // something a prefix can tell you. It matters because a code over
    // Telegram costs a cent and one over an Afghan carrier costs about
    // forty-five, against a budget of roughly a hundred and ten messages a
    // month -- so every person who picks Telegram pays for forty-five who
    // cannot. SMS stays selected by default, because it is the one that
    // reaches a handset with no data at all.
    Text(
        strings["auth.channel.question"],
        style = MaterialTheme.typography.labelMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
    )
    Spacer(Modifier.height(Spacing.xs))
    ChannelTabs(state.channel) { onEvent(SignInEvent.ChannelChosen(it)) }

    Spacer(Modifier.height(Spacing.xl))

    // A phone number is always laid out left-to-right and in Latin digits, even
    // in an RTL screen: it is a sequence to be dialled, not prose. The label
    // above it stays where the screen's own direction puts it.
    PillField(
        value = state.phone,
        onValueChange = { onEvent(SignInEvent.PhoneChanged(Numerals.latin(it))) },
        label = strings["auth.field.phone"],
        placeholder = "0700 123 456",
        leadingIcon = Icons.Filled.Phone,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
        leftToRight = true,
    )

    Spacer(Modifier.height(Spacing.xl))

    PrimaryAction(
        label = strings["auth.action.send_code"],
        onClick = { onEvent(SignInEvent.RequestCode) },
        enabled = state.canSubmitPhone,
        loading = state.isSubmitting,
    )
}

/**
 * SMS or Telegram, as two tabs under one line.
 *
 * They were two filter chips, which read as two settings that could both be
 * on. Tabs say "one of these": the chosen one is bold and green with a 2dp
 * bar under it, the other is quiet, and both sit on one hairline so the pair
 * reads as a single control. Each is a full touch target, and a screen reader
 * hears two tabs and which is selected.
 */
@Composable
private fun ChannelTabs(selected: String, onSelect: (String) -> Unit) {
    val strings = LocalVelroStrings.current
    Box(Modifier.fillMaxWidth()) {
        // The track both tabs stand on.
        Box(
            Modifier
                .align(Alignment.BottomCenter)
                .fillMaxWidth()
                .height(1.dp)
                .background(MaterialTheme.colorScheme.outlineVariant),
        )
        Row(Modifier.fillMaxWidth().selectableGroup()) {
            for (choice in listOf(CHANNEL_SMS, CHANNEL_TELEGRAM)) {
                val on = selected == choice
                Column(
                    Modifier
                        .weight(1f)
                        .heightIn(min = Sizing.touchTarget)
                        .selectable(selected = on, role = Role.Tab, onClick = { onSelect(choice) }),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Bottom,
                ) {
                    Text(
                        strings[
                            if (choice == CHANNEL_SMS) "auth.channel.sms"
                            else "auth.channel.telegram"
                        ],
                        style = MaterialTheme.typography.bodyLarge,
                        fontWeight = if (on) FontWeight.Bold else FontWeight.Normal,
                        color = if (on) MaterialTheme.colorScheme.primary
                        else MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.padding(vertical = Spacing.sm),
                    )
                    Box(
                        Modifier
                            .fillMaxWidth()
                            .height(2.dp)
                            .background(
                                if (on) MaterialTheme.colorScheme.primary
                                else androidx.compose.ui.graphics.Color.Transparent,
                                RoundedCornerShape(Radius.pill),
                            ),
                    )
                }
            }
        }
    }
}

@Composable
private fun CodeStep(state: SignInUiState, onEvent: (SignInEvent) -> Unit) {
    val strings = LocalVelroStrings.current

    // Says what happened, not what the field is called -- the field carries its
    // own label, and a heading repeating it word for word left the screen
    // saying "verification code" twice with nothing telling the person a
    // message had actually gone out.
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            // Where it actually went, which is not always where it was asked
            // for: a Telegram code that could not be delivered arrives as an
            // SMS, and pointing at the wrong app is how somebody sits waiting
            // for a message that is already on their phone.
            strings[
                if (state.sentChannel == CHANNEL_TELEGRAM) "auth.hint.code_sent_telegram"
                else "auth.hint.code_sent"
            ],
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
            textAlign = TextAlign.Center,
        )
        Spacer(Modifier.height(Spacing.xs))
        Text(
            state.phone,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
    Spacer(Modifier.height(Spacing.xl))

    // Large and centred: four to eight digits read off another screen, the
    // one thing on this step, and compared character by character.
    PillField(
        value = state.code,
        onValueChange = { onEvent(SignInEvent.CodeChanged(Numerals.latin(it))) },
        label = strings["auth.field.code"],
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
        textStyle = MaterialTheme.typography.headlineSmall.copy(
            textAlign = TextAlign.Center,
            fontWeight = FontWeight.Bold,
            letterSpacing = 6.sp,
        ),
        leftToRight = true,
    )

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

/**
 * The answer to "delete my account", on the first screen after it.
 *
 * Without it a deletion looks exactly like a session that ran out: the app is
 * simply on sign-in again, and nothing says whether the account went or the
 * connection did. A live region too, for somebody who deleted the account by
 * ear.
 */
@Composable
private fun AccountDeletedNotice() {
    val strings = LocalVelroStrings.current
    Surface(
        color = MaterialTheme.colorScheme.primaryContainer,
        contentColor = MaterialTheme.colorScheme.onPrimaryContainer,
        shape = RoundedCornerShape(Radius.surface),
        modifier = Modifier
            .fillMaxWidth()
            .semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite },
    ) {
        Row(
            Modifier.padding(Spacing.lg),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(
                Icons.Filled.CheckCircle,
                contentDescription = null,
                modifier = Modifier.size(Sizing.iconMd),
            )
            Spacer(Modifier.size(Spacing.sm))
            Text(
                strings["account.delete.done"],
                style = MaterialTheme.typography.bodyMedium,
            )
        }
    }
}

@Composable
private fun LanguagePicker(selected: Locale, onSelect: (Locale) -> Unit) {
    // Language comes first, before anything else in the form: a passenger who
    // cannot read the form cannot fill it in.
    Row(horizontalArrangement = Arrangement.spacedBy(Spacing.sm)) {
        for (locale in listOf(Locale.DARI, Locale.PASHTO, Locale.ENGLISH)) {
            ChoiceChip(
                selected = locale == selected,
                onClick = { onSelect(locale) },
                label = locale.displayName(),
            )
        }
    }
}

private fun Locale.displayName(): String = when (this) {
    Locale.DARI -> "دری"
    Locale.PASHTO -> "پښتو"
    Locale.ENGLISH -> "English"
}
