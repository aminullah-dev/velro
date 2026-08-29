package af.velro.feature.driver

import af.velro.core.i18n.Calendars
import af.velro.core.ui.component.ErrorState
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import af.velro.domain.DocumentChecklist
import af.velro.domain.DocumentStatus
import af.velro.domain.DriverDocument
import android.content.Context
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun DocumentsRoute(viewModel: DocumentsViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    DocumentsScreen(state, viewModel::onEvent)
}

@Composable
fun DocumentsScreen(
    state: DocumentsUiState,
    onEvent: (DocumentsEvent) -> Unit,
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current
    val context = LocalContext.current
    var pendingType by remember { mutableStateOf<String?>(null) }

    // The system photo picker. It needs no permission and shows only what the
    // person chooses, which matters for a screen about identity documents --
    // the app never gets access to the whole gallery.
    val picker = rememberLauncherForActivityResult(
        ActivityResultContracts.PickVisualMedia()
    ) { uri: Uri? ->
        val kind = pendingType
        pendingType = null
        if (uri == null || kind == null) return@rememberLauncherForActivityResult
        val read = readImage(context, uri)
        if (read != null) {
            onEvent(DocumentsEvent.Upload(kind, read.first, read.second))
        }
    }

    if (state.isLoading) {
        LoadingState(modifier)
        return
    }

    val checklist = state.checklist
    if (checklist == null) {
        // Not a driver yet: the screen offers the one action that makes sense.
        Column(
            modifier
                .fillMaxSize()
                .padding(horizontal = Spacing.gutter, vertical = Spacing.xl),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                strings["driver.documents.not_a_driver"],
                style = MaterialTheme.typography.bodyLarge,
            )
            Spacer(Modifier.height(Spacing.lg))
            PrimaryAction(
                label = strings["driver.documents.apply"],
                onClick = { onEvent(DocumentsEvent.RegisterAsDriver) },
            )
            if (state.errorCode != null) {
                InlineError(state.errorCode!!, context = state.errorContext)
            }
        }
        return
    }

    Column(
        modifier
            .fillMaxSize()
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = Spacing.gutter, vertical = Spacing.lg)
    ) {
        Text(
            strings["driver.documents.title"],
            style = MaterialTheme.typography.titleLarge,
        )
        Spacer(Modifier.height(Spacing.sm))
        Text(
            strings[statusHeadlineKey(checklist)],
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        if (state.errorCode != null) {
            InlineError(state.errorCode!!, context = state.errorContext)
        }

        Spacer(Modifier.height(Spacing.lg))

        for (kind in checklist.required) {
            DocumentRow(
                typeCode = kind,
                document = checklist.currentFor(kind),
                uploading = state.uploadingType == kind,
                enabled = !state.isUploading,
                onPick = {
                    pendingType = kind
                    picker.launch(
                        PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)
                    )
                },
            )
            Spacer(Modifier.height(Spacing.sm))
        }
    }
}

private fun statusHeadlineKey(checklist: DocumentChecklist): String = when {
    checklist.canWork -> "driver.documents.approved"
    checklist.awaitingReview -> "driver.documents.awaiting_review"
    else -> "driver.documents.incomplete"
}

@Composable
private fun DocumentRow(
    typeCode: String,
    document: DriverDocument?,
    uploading: Boolean,
    enabled: Boolean,
    onPick: () -> Unit,
) {
    val strings = LocalVelroStrings.current

    VelroCard {
        Column {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    strings["document.type.${typeCode.lowercase()}"],
                    style = MaterialTheme.typography.bodyLarge,
                    fontWeight = FontWeight.Medium,
                )
                DocumentStatusLabel(document)
            }

            if (document?.rejectionReason != null) {
                Spacer(Modifier.height(Spacing.sm))
                // The reason is the whole point of showing this at all: a driver
                // told only "rejected" sends the same photograph again.
                Text(
                    document.rejectionReason!!,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.error,
                )
            }

            if (document != null) {
                Spacer(Modifier.height(Spacing.xs))
                Text(
                    Calendars.date(document.uploadedAt, strings.locale),
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            Spacer(Modifier.height(Spacing.md))
            SecondaryAction(
                label = strings[
                    if (document == null) "driver.documents.send"
                    else "driver.documents.replace"
                ],
                onClick = onPick,
                enabled = enabled && !uploading,
            )
        }
    }
}

@Composable
private fun DocumentStatusLabel(document: DriverDocument?) {
    val strings = LocalVelroStrings.current
    val (key, colour) = when (document?.status) {
        null -> "driver.documents.not_sent" to MaterialTheme.colorScheme.onSurfaceVariant
        DocumentStatus.VERIFIED -> "document.status.verified" to MaterialTheme.colorScheme.primary
        DocumentStatus.PENDING -> "document.status.pending" to MaterialTheme.colorScheme.secondary
        DocumentStatus.REJECTED -> "document.status.rejected" to MaterialTheme.colorScheme.error
        DocumentStatus.EXPIRED -> "document.status.expired" to MaterialTheme.colorScheme.error
    }
    Text(strings[key], style = MaterialTheme.typography.labelSmall, color = colour)
}

/**
 * Read the chosen image into memory.
 *
 * Bounded deliberately: a modern phone camera produces files larger than the
 * server accepts, and reading an arbitrary one into a byte array on a cheap
 * handset is how an app runs out of memory. Anything oversized is refused here
 * rather than sent and rejected after a long upload on a slow connection.
 */
private fun readImage(context: Context, uri: Uri): Pair<ByteArray, String>? = runCatching {
    val type = context.contentResolver.getType(uri) ?: "image/jpeg"
    val bytes = context.contentResolver.openInputStream(uri)?.use { stream ->
        stream.readBytes()
    } ?: return null
    if (bytes.size > MAX_UPLOAD_BYTES) return null
    bytes to type
}.getOrNull()

private const val MAX_UPLOAD_BYTES = 6 * 1024 * 1024
