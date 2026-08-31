package af.velro.feature.driver

import af.velro.core.i18n.Calendars
import af.velro.core.ui.component.ErrorState
import af.velro.core.ui.component.InlineMessage
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.component.VelroScreen
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import af.velro.domain.DocumentChecklist
import af.velro.domain.DocumentStatus
import af.velro.domain.DriverDocument
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
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
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.core.content.FileProvider
import androidx.compose.ui.text.font.FontWeight
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun DocumentsRoute(
    onBack: () -> Unit = {},
    viewModel: DocumentsViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    DocumentsScreen(state, viewModel::onEvent, onBack = onBack)
}

@Composable
fun DocumentsScreen(
    state: DocumentsUiState,
    onEvent: (DocumentsEvent) -> Unit,
    onBack: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current
    val context = LocalContext.current
    // Saveable, not remembered.
    //
    // The camera is another app, and Android is free to destroy this one
    // behind it -- which on the cheap handsets VELRO is built for is the
    // ordinary case, not the edge. Held in `remember`, both of these came back
    // null, and both callbacks bail out silently when they do: the driver
    // photographed his licence, watched the app return, and found nothing had
    // happened and nothing said why.
    var pendingType by rememberSaveable { mutableStateOf<String?>(null) }
    // A problem the app found by itself, which has no server error code.
    var localProblem by remember { mutableStateOf<String?>(null) }

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
        } else {
            // Silence here is what made this a defect: a driver tapped, waited,
            // and the screen did not change.
            localProblem = "driver.documents.too_large"
        }
    }

    // The face is taken now, not chosen.
    //
    // A photo picked from the gallery could be anyone's -- which is precisely
    // what the check exists to catch. The camera is the whole point of asking
    // for it, so the selfie has its own launcher and the gallery is not offered.
    //
    // TakePicture, not TakePicturePreview: the preview contract returns a
    // thumbnail of a couple of hundred pixels, which nobody can compare against
    // a tazkira. This writes the full image to a file the app owns.
    // The path, not the File: a String survives being written to a Bundle and
    // the File and content URI are rebuilt from it.
    var capturePath by rememberSaveable { mutableStateOf<String?>(null) }
    val captureTarget = capturePath?.let { captureFrom(context, java.io.File(it)) }
    val camera = rememberLauncherForActivityResult(
        ActivityResultContracts.TakePicture()
    ) { taken: Boolean ->
        val kind = pendingType
        val target = captureTarget
        pendingType = null
        capturePath = null
        if (!taken || kind == null || target == null) return@rememberLauncherForActivityResult
        val read = readImage(context, target.uri)
        if (read != null) {
            onEvent(DocumentsEvent.Upload(kind, read.first, read.second))
        } else {
            localProblem = "driver.documents.too_large"
        }
        // Deleted as soon as it is read. A face photograph sitting in the cache
        // outlives its purpose the moment the upload has the bytes.
        runCatching { target.file.delete() }
    }

    if (state.isLoading) {
        LoadingState(modifier)
        return
    }

    val checklist = state.checklist
    // A failure is not an answer.
    //
    // Only DRIVER_NOT_FOUND and PERMISSION_DENIED mean "not a driver yet";
    // every other failure leaves `checklist` null too, and this branched on
    // the null alone. So an approved driver opening his papers on a weak
    // connection was told he was not registered as a driver and offered the
    // application form again -- with no error, no retry, and nothing to
    // suggest the app had simply failed to ask.
    if (checklist == null && state.errorCode != null) {
        VelroScreen(
            title = strings["driver.documents.title"],
            onBack = onBack,
            modifier = modifier,
        ) {
            ErrorState(
                errorCode = state.errorCode!!,
                context = state.errorContext,
                onRetry = { onEvent(DocumentsEvent.Refresh) },
            )
        }
        return
    }
    if (checklist == null) {
        // Not a driver yet: the screen offers the one action that makes
        // sense, and a way back, which this branch did not have at all.
        VelroScreen(
            title = strings["driver.documents.title"],
            onBack = onBack,
            modifier = modifier,
        ) {
            Text(
                strings["driver.documents.not_a_driver"],
                style = MaterialTheme.typography.bodyLarge,
            )
            Spacer(Modifier.height(Spacing.lg))

            // The one moment he is already telling VELRO who he is: the screen
            // after this asks him to photograph his tazkira.
            //
            // No LTR wrapper, unlike the phone and the plate elsewhere -- a
            // name is written in the direction of the language it is in. And no
            // Numerals fold: that is right for a plate and wrong for a person.
            OutlinedTextField(
                value = state.typedName,
                onValueChange = { onEvent(DocumentsEvent.NameChanged(it)) },
                label = { Text(strings["profile.field.name"]) },
                supportingText = { Text(strings["profile.hint.name_driver"]) },
                singleLine = true,
                enabled = !state.isLoading,
                modifier = Modifier.fillMaxWidth(),
            )
            Text(
                strings["profile.hint.name_optional"],
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(top = Spacing.xs),
            )

            Spacer(Modifier.height(Spacing.lg))
            PrimaryAction(
                // Always enabled. The field is optional, and an empty one is
                // the way past it -- a disabled button in front of a man who
                // cannot write would end his application here.
                label = strings["driver.documents.apply"],
                onClick = { onEvent(DocumentsEvent.RegisterAsDriver) },
                loading = state.isLoading,
                modifier = Modifier.fillMaxWidth(),
            )
            if (state.errorCode != null) {
                InlineError(state.errorCode!!, context = state.errorContext)
            }
        }
        return
    }

    VelroScreen(
        title = strings["driver.documents.title"],
        onBack = onBack,
        modifier = modifier,
    ) {
        // The title moved into the bar, so it is not repeated here.
        Spacer(Modifier.height(Spacing.sm))
        localProblem?.let { InlineMessage(it) }
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
                    if (kind == SELFIE) {
                        val target = newCapture(context)
                        capturePath = target.file.absolutePath
                        camera.launch(target.uri)
                    } else {
                        picker.launch(
                            PickVisualMediaRequest(
                                ActivityResultContracts.PickVisualMedia.ImageOnly
                            )
                        )
                    }
                },
            )
            Spacer(Modifier.height(Spacing.sm))
        }
    }
}

/** The one document that must be taken rather than chosen. */
private const val SELFIE = "SELFIE"

/**
 * A file the camera app may write to, inside this app's cache.
 *
 * Not the shared gallery: an identity photograph should not end up somewhere
 * every other app on the phone can read, or where it turns up while the owner
 * is showing someone their pictures.
 */
private data class Capture(val file: java.io.File, val uri: Uri)

/** The content URI for a capture file the app already owns. */
private fun captureFrom(context: Context, file: java.io.File): Capture =
    Capture(file, FileProvider.getUriForFile(context, "${'$'}{context.packageName}.captures", file))

private fun newCapture(context: Context): Capture {
    val dir = java.io.File(context.cacheDir, "captures").apply { mkdirs() }
    val file = java.io.File.createTempFile("selfie", ".jpg", dir)
    // The real File is kept alongside the content URI: the URI's path belongs
    // to the provider, not the filesystem, so it cannot be used to delete.
    return Capture(file, FileProvider.getUriForFile(context, "${context.packageName}.captures", file))
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
                // Said, not just shown.
                //
                // A bare date sat here in the same size and colour as the
                // expiry line directly beneath it, so a card could carry two
                // dates with only one of them labelled -- and on a screen
                // about whether papers are still valid, "8 Sunbula" is a
                // different fact depending on which one it is.
                Text(
                    strings[
                        "driver.documents.sent_on",
                        "date" to Calendars.date(document.uploadedAt, strings.locale),
                    ],
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            // The expiry, said out loud and early.
            //
            // A licence or a جواز سیر that has run out stops the driver from
            // going online. Without this line the first they learn of it is
            // being refused at the start of a shift, with a passenger already
            // waiting -- and nothing on the screen to explain it. The warning
            // window exists so the replacement can be sent before that morning
            // rather than after it.
            document?.expiresOn?.let { expiry ->
                val notice = expiryNotice(expiry, java.time.LocalDate.now(Calendars.KABUL))
                if (notice != null) {
                    val shown = Calendars.date(
                        java.time.LocalDate.parse(expiry)
                            .atStartOfDay(Calendars.KABUL).toInstant(),
                        strings.locale,
                    )
                    Spacer(Modifier.height(Spacing.xs))
                    Text(
                        strings[notice.messageKey, "date" to shown],
                        style = MaterialTheme.typography.labelSmall,
                        color = when (notice.severity) {
                            ExpirySeverity.PAST -> MaterialTheme.colorScheme.error
                            ExpirySeverity.SOON -> MaterialTheme.colorScheme.secondary
                            ExpirySeverity.FINE -> MaterialTheme.colorScheme.onSurfaceVariant
                        },
                    )
                }
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
    val bytes = context.contentResolver.openInputStream(uri)?.use { stream ->
        stream.readBytes()
    } ?: return null
    if (bytes.size <= MAX_UPLOAD_BYTES) {
        return@runCatching bytes to (context.contentResolver.getType(uri) ?: "image/jpeg")
    }

    // Too big to send, so shrink it rather than refuse it. A modern phone
    // camera routinely produces more than six megabytes, and refusing meant a
    // driver tapped, waited, and saw nothing at all -- the callers had no else
    // branch. Refusing is also the wrong answer: he cannot make his camera take
    // a smaller photograph, so it would end his application.
    //
    // inSampleSize halves in powers of two and decodes at that size, so the
    // full image is never held in memory on a cheap handset.
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
    var sample = 1
    while (bounds.outWidth / sample > MAX_EDGE_PX || bounds.outHeight / sample > MAX_EDGE_PX) {
        sample *= 2
    }
    val bitmap = BitmapFactory.decodeByteArray(
        bytes, 0, bytes.size, BitmapFactory.Options().apply { inSampleSize = sample },
    ) ?: return null

    val out = java.io.ByteArrayOutputStream()
    // 85 keeps a tazkira's small print legible; a reviewer has to read a number
    // off it, and that is the whole purpose of the upload.
    bitmap.compress(Bitmap.CompressFormat.JPEG, 85, out)
    bitmap.recycle()
    val shrunk = out.toByteArray()
    if (shrunk.size > MAX_UPLOAD_BYTES) return null
    shrunk to "image/jpeg"
}.getOrNull()

private const val MAX_UPLOAD_BYTES = 6 * 1024 * 1024

/** Long edge after downscaling. A tazkira is legible well below this. */
private const val MAX_EDGE_PX = 2048

/** How close a document is to running out. */
internal enum class ExpirySeverity { PAST, SOON, FINE }

/**
 * Which sentence to show under a document, and how loudly.
 *
 * Returns a message key rather than a rendered string so the rule can be
 * tested without an Android context -- and so the wording stays in the locale
 * files, where every other sentence lives.
 */
internal data class ExpiryNotice(val messageKey: String, val severity: ExpirySeverity)

/**
 * Thirty days is the warning window: long enough to reach an office in a
 * valley where that is a day's travel, short enough that the line is not
 * permanently on screen and stops being read.
 *
 * Returns null for a date that cannot be parsed rather than guessing. A
 * malformed expiry rendered as "expired" would tell a driver holding a valid
 * licence to stop working.
 */
internal fun expiryNotice(
    expiresOn: String,
    today: java.time.LocalDate,
): ExpiryNotice? {
    val expiry = runCatching { java.time.LocalDate.parse(expiresOn) }.getOrNull() ?: return null
    val daysLeft = java.time.temporal.ChronoUnit.DAYS.between(today, expiry)
    return when {
        daysLeft < 0 -> ExpiryNotice("driver.documents.expired", ExpirySeverity.PAST)
        daysLeft <= WARN_WITHIN_DAYS ->
            ExpiryNotice("driver.documents.expiring_soon", ExpirySeverity.SOON)
        else -> ExpiryNotice("driver.documents.valid_until", ExpirySeverity.FINE)
    }
}

internal const val WARN_WITHIN_DAYS = 30L
