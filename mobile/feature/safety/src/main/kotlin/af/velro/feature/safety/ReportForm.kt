package af.velro.feature.safety

import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection

/**
 * Tell VELRO what happened.
 *
 * The last of the three doors and deliberately the least prominent. It needs a
 * connection, it reaches a small team who are not always awake, and the screen
 * says both of those things before the button rather than after it.
 *
 * The categories come from the server's own list -- cached, with a compiled-in
 * copy behind it -- because `SupportTicket` rejects anything outside its
 * frozenset. A form offering a category the domain refuses is a form that fails
 * on submit for somebody who has just described being in danger.
 */
@Composable
internal fun ReportForm(
    state: ReportUiState,
    contacts: af.velro.domain.SafetyContacts,
    onCategoryChosen: (String) -> Unit,
    onBodyChanged: (String) -> Unit,
    onSubmit: () -> Unit,
    onBack: () -> Unit,
) {
    val strings = LocalVelroStrings.current

    Column(verticalArrangement = Arrangement.spacedBy(Spacing.md)) {
        Text(
            strings["safety.report"],
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
        )

        // Said before the form, not after it. Somebody in danger right now
        // should be dialling, and this is where they find that out.
        Text(
            strings[
                "safety.report_hint",
                "number" to (contacts.emergencyNumbers.firstOrNull() ?: ""),
            ],
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        val reference = state.reference
        if (reference != null) {
            // The reference is the only thing they keep. Latin and unmirrored,
            // because it is read down a phone line to an operator.
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                Text(
                    reference,
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                )
            }
            Text(
                strings["safety.report_sent", "reference" to reference],
                style = MaterialTheme.typography.bodyMedium,
            )
            SecondaryAction(
                label = strings["common.action.close"],
                onClick = onBack,
                modifier = Modifier.fillMaxWidth(),
            )
            return@Column
        }

        if (state.errorCode != null) {
            InlineError(state.errorCode, context = state.errorContext)
        }

        for (category in contacts.categories) {
            Row(
                Modifier
                    .fillMaxWidth()
                    .clickable { onCategoryChosen(category) }
                    .padding(vertical = Spacing.xs),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                RadioButton(
                    selected = state.categoryCode == category,
                    onClick = { onCategoryChosen(category) },
                )
                Spacer(Modifier.width(Spacing.sm))
                Text(strings["ticket.category.${category.lowercase()}"])
            }
        }

        OutlinedTextField(
            value = state.body,
            onValueChange = onBodyChanged,
            // The passenger's own words, not the operator's. This field used
            // to carry admin.support.reply_placeholder -- "What are you
            // telling them?" -- which is what an operator is asked, and reads
            // as nonsense to somebody describing what happened to them.
            label = { Text(strings["safety.report_placeholder"]) },
            minLines = 3,
            modifier = Modifier.fillMaxWidth(),
        )

        Spacer(Modifier.height(Spacing.xs))
        PrimaryAction(
            label = strings["safety.report"],
            onClick = onSubmit,
            enabled = state.canSubmit,
            loading = state.isSending,
            modifier = Modifier.fillMaxWidth(),
        )
        SecondaryAction(
            label = strings["common.action.back"],
            onClick = onBack,
            modifier = Modifier.fillMaxWidth(),
        )
    }
}
