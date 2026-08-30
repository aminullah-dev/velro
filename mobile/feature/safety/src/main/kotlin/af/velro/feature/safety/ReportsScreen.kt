package af.velro.feature.safety

import af.velro.core.i18n.Calendars
import af.velro.core.ui.component.EmptyState
import af.velro.core.ui.component.ErrorState
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import af.velro.domain.SupportTicket
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

/**
 * What you told VELRO, and what VELRO said back.
 *
 * The report used to be a one-way door: the backend wrote the reply, tested it,
 * and put a line in the inbox, and nothing on the handset could open it. The
 * reference on the success screen was destroyed by that screen's only button,
 * so a person who pressed Close had no way back to their own report.
 */
@Composable
fun ReportsRoute(viewModel: ReportsViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    ReportsScreen(state, viewModel::onEvent)
}

@Composable
fun ReportsScreen(
    state: ReportsUiState,
    onEvent: (ReportsEvent) -> Unit,
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current

    if (state.isLoading && state.reports.isEmpty()) {
        LoadingState(modifier.fillMaxSize())
        return
    }
    if (state.errorCode != null && state.reports.isEmpty()) {
        ErrorState(
            errorCode = state.errorCode!!,
            context = state.errorContext,
            onRetry = { onEvent(ReportsEvent.Refresh) },
            modifier = modifier.fillMaxSize(),
        )
        return
    }

    Column(
        modifier
            .fillMaxSize()
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
            .imePadding()
            .padding(horizontal = Spacing.gutter, vertical = Spacing.lg),
    ) {
        Text(
            strings["safety.my_reports"],
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(Spacing.md))

        if (state.reports.isEmpty()) {
            EmptyState(messageKey = "safety.no_reports")
            return@Column
        }

        for (report in state.reports) {
            ReportCard(
                report = report,
                expanded = state.openId == report.id,
                draft = if (state.openId == report.id) state.draft else "",
                isSending = state.isSending,
                errorCode = if (state.openId == report.id) state.replyErrorCode else null,
                onToggle = { onEvent(ReportsEvent.Toggle(report.id)) },
                onDraftChanged = { onEvent(ReportsEvent.DraftChanged(it)) },
                onSend = { onEvent(ReportsEvent.Send(report.id)) },
            )
            Spacer(Modifier.height(Spacing.sm))
        }
    }
}

@Composable
private fun ReportCard(
    report: SupportTicket,
    expanded: Boolean,
    draft: String,
    isSending: Boolean,
    errorCode: String?,
    onToggle: () -> Unit,
    onDraftChanged: (String) -> Unit,
    onSend: () -> Unit,
) {
    val strings = LocalVelroStrings.current

    VelroCard {
        Column(Modifier.fillMaxWidth().clickable { onToggle() }) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                // A reference is read down a phone line to an operator: never
                // mirrored, never in Eastern digits.
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                    Text(
                        report.reference,
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold,
                    )
                }
                Text(
                    strings["ticket.status.${report.status.name.lowercase()}"],
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(
                strings["ticket.category.${report.categoryCode.lowercase()}"],
                style = MaterialTheme.typography.bodyMedium,
            )
            Text(
                Calendars.date(report.createdAt, strings.locale),
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            if (!expanded) {
                if (!report.hasAnswer) {
                    Spacer(Modifier.height(Spacing.xs))
                    Text(
                        strings["safety.awaiting_answer"],
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                return@Column
            }

            Spacer(Modifier.height(Spacing.md))
            for (message in report.messages) {
                Text(
                    strings[
                        if (message.isFromReporter) "safety.from_you"
                        else "safety.from_velro"
                    ],
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
                Text(message.body, style = MaterialTheme.typography.bodyMedium)
                Spacer(Modifier.height(Spacing.sm))
            }

            if (errorCode != null) {
                InlineError(errorCode)
                Spacer(Modifier.height(Spacing.sm))
            }

            if (report.canReply) {
                OutlinedTextField(
                    value = draft,
                    onValueChange = onDraftChanged,
                    label = { Text(strings["safety.reply_placeholder"]) },
                    minLines = 2,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(Spacing.sm))
                PrimaryAction(
                    label = strings["safety.reply"],
                    onClick = onSend,
                    enabled = !isSending && draft.trim().isNotEmpty(),
                    loading = isSending,
                    modifier = Modifier.fillMaxWidth(),
                )
            } else {
                // Closed. The server refuses a message here, so the field is
                // not offered rather than shown and then rejected.
                Text(
                    strings["safety.closed_note"],
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}
