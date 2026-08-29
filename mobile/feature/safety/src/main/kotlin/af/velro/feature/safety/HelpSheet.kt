package af.velro.feature.safety

import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

/**
 * What the ride is, for reading out loud.
 *
 * Everything here is already cached on the handset, so the sheet renders with
 * no connection at all. Passed in rather than fetched for the same reason: the
 * caller already has it on screen.
 */
data class RideFacts(
    val bookingNumber: String,
    val driverName: String?,
    val plate: String?,
    val origin: String?,
    val destination: String?,
)

/**
 * Get help.
 *
 * Three doors, in the order a person in trouble needs them:
 *
 * 1. Dial 119 or 100. Zero bytes, no permission, works on a phone that has
 *    never reached VELRO. This is first because it is the only one that brings
 *    anybody.
 * 2. Send the car's details to somebody who will actually come. The message is
 *    written for them; they choose the recipient in their own SMS app, so no
 *    contact list ever leaves the handset and VELRO never holds a list of which
 *    women in Ghorband have which male relatives.
 * 3. Tell VELRO. Needs data, and the button says out loud that nobody may read
 *    it until morning.
 *
 * Above all three, the sentence that makes the rest honest: VELRO is not an
 * emergency service and cannot send anyone. A button that implies rescue and
 * delivers a database row is worse than no button.
 */
@Composable
fun HelpSheet(
    ride: RideFacts?,
    onDismiss: () -> Unit,
    /** Attached to the report so an operator knows which journey it is about. */
    tripId: String? = null,
    bookingId: String? = null,
    /** Overrides the built-in form, for a caller that has its own screen. */
    onReport: (() -> Unit)? = null,
    viewModel: HelpViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = sheetState) {
        val report = state.report
        if (report == null) {
            HelpSheetContent(
                contacts = state.contacts,
                ride = ride,
                // The report door only appears when there is somewhere for it
                // to go. A button wired to nothing is the thing this whole
                // feature exists to avoid.
                onReport = if (onReport != null) onReport else viewModel::openReport,
            )
        } else {
            Column(
                Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState())
                    .navigationBarsPadding()
                    .padding(horizontal = Spacing.lg)
                    .padding(bottom = Spacing.xl),
            ) {
                ReportForm(
                    state = report,
                    contacts = state.contacts,
                    onCategoryChosen = viewModel::chooseCategory,
                    onBodyChanged = viewModel::changeBody,
                    onSubmit = { viewModel.submitReport(tripId, bookingId) },
                    onBack = viewModel::closeReport,
                )
            }
        }
    }
}

@Composable
internal fun HelpSheetContent(
    contacts: af.velro.domain.SafetyContacts,
    ride: RideFacts?,
    onReport: (() -> Unit)?,
    context: Context = LocalContext.current,
) {
    val strings = LocalVelroStrings.current

    Column(
        Modifier
            .fillMaxWidth()
            .verticalScroll(rememberScrollState())
            .navigationBarsPadding()
            .padding(horizontal = Spacing.lg)
            .padding(bottom = Spacing.xl),
        verticalArrangement = Arrangement.spacedBy(Spacing.md),
    ) {
        Text(
            strings["safety.title"],
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.SemiBold,
        )
        // First, before any button, so it is read before anything is pressed.
        Text(
            strings["safety.not_rescue"],
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        // 1. The numbers that bring somebody.
        for (number in contacts.emergencyNumbers) {
            PrimaryAction(
                label = strings["safety.call_emergency", "number" to number],
                onClick = { context.dial(number) },
                modifier = Modifier.fillMaxWidth(),
            )
        }
        if (contacts.emergencyNumbers.isNotEmpty()) {
            Text(
                strings["safety.call_emergency_hint"],
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        // 2. Somebody who will actually come.
        if (ride != null) {
            SecondaryAction(
                label = strings["safety.tell_someone"],
                onClick = { context.composeSms(smsBody(ride, strings)) },
                modifier = Modifier.fillMaxWidth(),
            )
            Text(
                strings["safety.tell_someone_hint"],
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            Spacer(Modifier.height(Spacing.sm))
            RideDetails(ride)
        } else {
            Text(
                strings["safety.no_ride"],
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }

        // 3. VELRO, last, and honest about the wait.
        if (onReport != null) {
            Spacer(Modifier.height(Spacing.sm))
            SecondaryAction(
                label = strings["safety.report"],
                onClick = onReport,
                modifier = Modifier.fillMaxWidth(),
            )
            Text(
                strings[
                    "safety.report_hint",
                    "number" to (contacts.emergencyNumbers.firstOrNull() ?: ""),
                ],
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * The card someone reads down a phone line.
 *
 * Not decoration: on a call to 119 or to a relative, these five facts are what
 * is asked for, and reading them off a screen beats remembering them.
 */
@Composable
private fun RideDetails(ride: RideFacts) {
    val strings = LocalVelroStrings.current
    VelroCard {
        Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
            Text(
                strings["safety.details_title"],
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.Medium,
            )
            ride.plate?.let {
                // A number plate is read off a physical car. Never mirrored,
                // never in Eastern digits, whatever the app locale.
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                    Text(
                        it,
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold,
                    )
                }
            }
            ride.driverName?.let {
                Text(it, style = MaterialTheme.typography.bodyLarge)
            }
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                Text(ride.bookingNumber, style = MaterialTheme.typography.bodyMedium)
            }
            if (ride.origin != null && ride.destination != null) {
                Text(
                    strings[
                        "ride.journey.from_to",
                        "origin" to ride.origin,
                        "destination" to ride.destination,
                    ],
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
            Text(
                strings["safety.read_aloud"],
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

/**
 * The message, written for them.
 *
 * A frightened person should not be composing a sentence. The recipient is
 * chosen in their own SMS app -- VELRO never sees it, never stores it, and
 * never holds a list of who a person would call for help.
 */
internal fun smsBody(ride: RideFacts, strings: af.velro.core.i18n.Strings): String =
    strings[
        "safety.sms_body",
        "plate" to (ride.plate ?: "—"),
        "driver" to (ride.driverName ?: "—"),
        "booking" to ride.bookingNumber,
        "origin" to (ride.origin ?: "—"),
        "destination" to (ride.destination ?: "—"),
    ]

/**
 * ACTION_DIAL, never ACTION_CALL.
 *
 * The dialler opens with the number filled in and the person presses call. No
 * CALL_PHONE permission, so no permission dialog at the worst possible moment,
 * and the app never places a call somebody did not see.
 */
private fun Context.dial(number: String) {
    runCatching {
        startActivity(
            Intent(Intent.ACTION_DIAL, Uri.parse("tel:$number"))
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }
}

private fun Context.composeSms(body: String) {
    runCatching {
        startActivity(
            Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:"))
                .putExtra("sms_body", body)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        )
    }
}
