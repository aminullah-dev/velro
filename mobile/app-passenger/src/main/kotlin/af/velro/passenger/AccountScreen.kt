package af.velro.passenger

import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateOf
import af.velro.core.ui.component.ConfirmDialog
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.i18n.Calendars
import af.velro.core.i18n.Numerals
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.PhotoAvatar
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.component.VelroScreen
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Radius
import af.velro.core.ui.theme.Sizing
import af.velro.core.ui.theme.Spacing
import af.velro.domain.Locale
import af.velro.domain.UserProfile
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun AccountRoute(
    onSignOut: () -> Unit,
    onBack: () -> Unit,
    viewModel: AccountViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val profile = state.profile

    if (profile == null) {
        LoadingState()
        return
    }
    AccountScreen(
        profile = profile,
        draftName = state.draftName,
        isSaving = state.isSaving,
        saved = state.saved,
        errorCode = state.errorCode,
        errorContext = state.errorContext,
        onNameChanged = viewModel::onNameChanged,
        onSaveName = viewModel::saveName,
        onLocaleChanged = viewModel::changeLocale,
        onSignOut = onSignOut,
        onBack = onBack,
    )
}

/**
 * The passenger's own account.
 *
 * The driver app grew a profile; the passenger app had none at all. A
 * passenger could see her journeys and nothing about herself -- not the name a
 * driver reads when he arrives, not the number the account belongs to, and not
 * the language the whole app is speaking to her in.
 *
 * That last one was the reason to build this now rather than later. The
 * language picker lived on the sign-in screen and nowhere else, and the choice
 * is stored and then drives everything -- so somebody who tapped the wrong
 * chip, or whose handset was set up by a son or a neighbour, was locked into a
 * language she could not read. The way out was to sign out, and the sign-out
 * button was labelled in the language she could not read.
 *
 * No badges and no tiers. The reference this is shaped from has both, and they
 * are engagement mechanics for a mature consumer product in a market with
 * competition to retain against. This is a screen for changing your name and
 * your language and seeing how many times you have travelled.
 */
@Composable
fun AccountScreen(
    profile: UserProfile,
    draftName: String,
    isSaving: Boolean,
    saved: Boolean,
    errorCode: String?,
    errorContext: Map<String, Any?>,
    onNameChanged: (String) -> Unit,
    onSaveName: () -> Unit,
    onLocaleChanged: (Locale) -> Unit,
    onSignOut: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current
    var confirming by rememberSaveable { mutableStateOf(false) }

    if (confirming) {
        // Confirmed because it wipes the local cache. On a handset shared in a
        // household that is right, and it is also unrecoverable without a
        // connection to sign back in. The dialog moved here with the button
        // rather than being left behind on the home screen with nothing able
        // to open it.
        ConfirmDialog(
            titleKey = "auth.action.sign_out",
            bodyKey = "auth.sign_out_warning",
            confirmKey = "auth.action.sign_out",
            onConfirm = { confirming = false; onSignOut() },
            onDismiss = { confirming = false },
        )
    }

    VelroScreen(
        title = strings["passenger.profile.title"],
        onBack = onBack,
        modifier = modifier,
    ) {
        Spacer(Modifier.height(Spacing.lg))

        Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
            // A silhouette, and no way to change it. A driver sends a
            // photograph because a passenger deciding whether to get into his
            // car is owed his face; the reverse does not carry the same weight,
            // and asking a woman in Ghorband for her photograph before she can
            // book a seat is a good way to lose her at the first screen.
            PhotoAvatar(bytes = null, size = Sizing.profilePhoto)
            Spacer(Modifier.height(Spacing.md))
            Text(
                profile.fullName?.takeIf { it.isNotBlank() }
                    ?: strings["common.value.no_name"],
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.SemiBold,
                textAlign = TextAlign.Center,
            )
        }

        Spacer(Modifier.height(Spacing.xl))

        Row(
            Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
        ) {
            Figure(
                value = Numerals.localise(profile.completedTrips.toString(), strings.locale),
                label = strings["passenger.profile.trips"],
                modifier = Modifier.weight(1f),
            )
            Figure(
                // Null until a driver has scored her, and shown as a dash
                // rather than 0.0 -- which would read as a bad passenger
                // rather than as a new one.
                value = profile.ratingAverage
                    ?.takeIf { profile.ratingCount > 0 }
                    ?.let {
                        Numerals.localise(
                            String.format(java.util.Locale.US, "%.1f", it), strings.locale,
                        )
                    } ?: "—",
                label = strings["driver.profile.rating"],
                modifier = Modifier.weight(1f),
            )
            Figure(
                // In the Shamsi calendar the rest of the product uses, and
                // guarded: an older record may have no timestamp, and a
                // profile is not worth crashing over a missing date.
                value = profile.memberSince
                    ?.let {
                        runCatching {
                            Calendars.date(java.time.Instant.parse(it), strings.locale)
                        }.getOrNull()
                    }
                    ?: "—",
                label = strings["passenger.profile.since"],
                modifier = Modifier.weight(1f),
            )
        }

        Spacer(Modifier.height(Spacing.lg))

        // The name, editable. PATCH /auth/me has always accepted it and no
        // screen in this app ever called it, so a passenger who signed up
        // without a name -- which is allowed -- could never add one, and the
        // driver arriving to collect her had nobody's name to ask for.
        VelroCard {
            Column {
                OutlinedTextField(
                    value = draftName,
                    onValueChange = onNameChanged,
                    label = { Text(strings["profile.field.name"]) },
                    supportingText = { Text(strings["profile.hint.name_optional"]) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(Spacing.md))
                PrimaryAction(
                    label = strings["common.action.save"],
                    onClick = onSaveName,
                    enabled = draftName != profile.fullName.orEmpty(),
                    loading = isSaving,
                    radius = Radius.pill,
                )
                if (saved) {
                    Spacer(Modifier.height(Spacing.sm))
                    Text(
                        strings["passenger.profile.name_saved"],
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.primary,
                    )
                }
            }
        }

        Spacer(Modifier.height(Spacing.lg))

        VelroCard {
            Column {
                Text(
                    strings["passenger.profile.language"],
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(
                    strings["passenger.profile.language_hint"],
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(Spacing.md))
                Row(horizontalArrangement = Arrangement.spacedBy(Spacing.sm)) {
                    for (option in listOf(Locale.DARI, Locale.PASHTO, Locale.ENGLISH)) {
                        FilterChip(
                            selected = option == profile.locale,
                            onClick = { onLocaleChanged(option) },
                            label = { Text(option.displayName()) },
                        )
                    }
                }
            }
        }

        Spacer(Modifier.height(Spacing.lg))

        VelroCard {
            Column {
                Text(
                    strings["passenger.profile.phone"],
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Spacer(Modifier.height(Spacing.xxs))
                Text(profile.phone, style = MaterialTheme.typography.bodyLarge)
                Spacer(Modifier.height(Spacing.xs))
                Text(
                    strings["passenger.profile.phone_hint"],
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }

        if (errorCode != null) {
            InlineError(errorCode, context = errorContext)
        }

        // Last, and on this screen rather than in the header.
        //
        // It used to sit beside the brand as an icon, one tap from every
        // screen, next to the help button -- which is a bad neighbour for a
        // control that wipes the local cache and needs a connection to undo.
        // Down here it is where somebody goes deliberately, after the things
        // they came for.
        Spacer(Modifier.height(Spacing.xl))
        SecondaryAction(
            label = strings["auth.action.sign_out"],
            onClick = { confirming = true },
        )

        Spacer(Modifier.height(Spacing.xl))
    }
}

@Composable
private fun Figure(value: String, label: String, modifier: Modifier = Modifier) {
    VelroCard(modifier = modifier) {
        Column {
            Text(
                value,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.size(Spacing.xxs))
            Text(
                label,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/** Hardcoded, like the sign-in picker: each reads the same in every locale. */
private fun Locale.displayName(): String = when (this) {
    Locale.DARI -> "دری"
    Locale.PASHTO -> "پښتو"
    Locale.ENGLISH -> "English"
}
