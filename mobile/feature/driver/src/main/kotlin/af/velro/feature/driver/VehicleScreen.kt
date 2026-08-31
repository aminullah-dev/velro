package af.velro.feature.driver

import af.velro.core.i18n.Numerals
import af.velro.core.ui.component.ErrorState
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.component.VelroScreen
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import af.velro.core.i18n.Calendars
import af.velro.domain.DocumentStatus
import af.velro.domain.Vehicle
import af.velro.domain.VehicleStatus
import af.velro.domain.VehicleChecklist
import af.velro.domain.VehicleDocument
import af.velro.domain.VehicleType
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.horizontalScroll
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
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.foundation.text.KeyboardOptions
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun VehicleRoute(
    onBack: () -> Unit = {},
    viewModel: VehicleViewModel = hiltViewModel(),
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    VehicleScreen(state, viewModel::onEvent, onBack = onBack)
}

@Composable
fun VehicleScreen(
    state: VehicleUiState,
    onEvent: (VehicleEvent) -> Unit,
    onBack: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    val strings = LocalVelroStrings.current

    if (state.isLoading) {
        LoadingState(modifier.fillMaxSize())
        return
    }
    // Nothing loaded and no types to offer: the form cannot be drawn at all.
    if (state.types.isEmpty() && state.errorCode != null) {
        ErrorState(
            errorCode = state.errorCode!!,
            context = state.errorContext,
            onRetry = { onEvent(VehicleEvent.Refresh) },
            modifier = modifier.fillMaxSize(),
        )
        return
    }

    VelroScreen(
        title = strings["driver.vehicle.title"],
        onBack = onBack,
        modifier = modifier,
    ) {
        // The title lives in the app bar now, not twice on the screen.

        state.vehicle?.let { VehicleSummary(it) }

        if (state.errorCode != null) {
            InlineError(state.errorCode!!, context = state.errorContext)
        }

        if (state.isEditing) {
            VehicleForm(state, onEvent)
        } else {
            SecondaryAction(
                label = strings["driver.vehicle.edit"],
                onClick = { onEvent(VehicleEvent.StartEditing) },
                modifier = Modifier.fillMaxWidth(),
            )
        }

        // The car's own papers, under the car they belong to. Deliberately not
        // on the driver's documents screen: a driver with two cars owes two
        // جواز سیر, and putting them in one list is what let the first
        // certify the second.
        state.papers?.let { papers ->
            Spacer(Modifier.height(Spacing.md))
            VehiclePapers(papers, state.uploadingPaper, onEvent)
        }

        Spacer(Modifier.height(Spacing.xl))
    }
}

@Composable
private fun VehicleSummary(vehicle: Vehicle) {
    val strings = LocalVelroStrings.current
    VelroCard {
        Column(verticalArrangement = Arrangement.spacedBy(Spacing.xs)) {
            // A number plate is read off a physical car. It is never mirrored
            // and never rendered in Eastern digits, whatever the app locale.
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                Text(
                    vehicle.plateNumber,
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                )
            }
            val described = vehicle.describedAs
            if (described.isNotBlank()) {
                Text(described, style = MaterialTheme.typography.bodyMedium)
            }
            Text(
                strings["driver.vehicle.seats_count", "count" to vehicle.seatCapacity],
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Text(
                when (vehicle.status) {
                    VehicleStatus.ACTIVE -> strings["driver.vehicle.active"]
                    VehicleStatus.PENDING -> strings["driver.vehicle.awaiting"]
                    VehicleStatus.SUSPENDED -> strings["driver.vehicle.suspended"]
                    VehicleStatus.RETIRED -> strings["driver.vehicle.retired"]
                },
                style = MaterialTheme.typography.bodyMedium,
                color = if (vehicle.isReadyForWork) MaterialTheme.colorScheme.primary
                else MaterialTheme.colorScheme.error,
            )
        }
    }
}

@Composable
private fun VehicleForm(state: VehicleUiState, onEvent: (VehicleEvent) -> Unit) {
    val strings = LocalVelroStrings.current

    if (state.vehicle == null) {
        Text(
            strings["driver.vehicle.none"],
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }

    Text(strings["driver.vehicle.type"], style = MaterialTheme.typography.labelLarge)
    Row(
        Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
        horizontalArrangement = Arrangement.spacedBy(Spacing.sm),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        state.types.forEach { type -> TypeChip(type, state.typeCode, onEvent) }
    }

    Spacer(Modifier.height(Spacing.xs))

    // Latin-only, upper case: the plate is a physical object, and folding the
    // driver's keyboard here saves the server from guessing later.
    OutlinedTextField(
        value = state.plate,
        onValueChange = { onEvent(VehicleEvent.PlateChanged(Numerals.latin(it).uppercase())) },
        label = { Text(strings["driver.vehicle.plate"]) },
        supportingText = { Text(strings["driver.vehicle.plate_hint"]) },
        singleLine = true,
        keyboardOptions = KeyboardOptions(
            capitalization = KeyboardCapitalization.Characters,
        ),
        modifier = Modifier.fillMaxWidth(),
    )

    OutlinedTextField(
        value = state.seats,
        onValueChange = { onEvent(VehicleEvent.SeatsChanged(Numerals.latin(it))) },
        label = { Text(strings["driver.vehicle.seats"]) },
        singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        modifier = Modifier.fillMaxWidth(),
    )

    Row(horizontalArrangement = Arrangement.spacedBy(Spacing.sm)) {
        OutlinedTextField(
            value = state.brand,
            onValueChange = { onEvent(VehicleEvent.BrandChanged(it)) },
            label = { Text(strings["driver.vehicle.brand"]) },
            singleLine = true,
            modifier = Modifier.weight(1f),
        )
        OutlinedTextField(
            value = state.model,
            onValueChange = { onEvent(VehicleEvent.ModelChanged(it)) },
            label = { Text(strings["driver.vehicle.model"]) },
            singleLine = true,
            modifier = Modifier.weight(1f),
        )
    }

    Row(horizontalArrangement = Arrangement.spacedBy(Spacing.sm)) {
        OutlinedTextField(
            value = state.year,
            onValueChange = { onEvent(VehicleEvent.YearChanged(Numerals.latin(it))) },
            label = { Text(strings["driver.vehicle.year"]) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
            modifier = Modifier.weight(1f),
        )
        OutlinedTextField(
            value = state.colour,
            onValueChange = { onEvent(VehicleEvent.ColourChanged(it)) },
            label = { Text(strings["driver.vehicle.colour"]) },
            singleLine = true,
            modifier = Modifier.weight(1f),
        )
    }

    Spacer(Modifier.height(Spacing.sm))

    PrimaryAction(
        label = strings["driver.vehicle.save"],
        onClick = { onEvent(VehicleEvent.Submit) },
        enabled = state.canSubmit,
        loading = state.isSaving,
        modifier = Modifier.fillMaxWidth(),
    )

    // Only offered once there is something to go back to.
    if (state.vehicle != null) {
        SecondaryAction(
            label = strings["common.action.cancel"],
            onClick = { onEvent(VehicleEvent.CancelEditing) },
            modifier = Modifier.fillMaxWidth(),
        )
    }
}

@Composable
private fun TypeChip(type: VehicleType, selected: String, onEvent: (VehicleEvent) -> Unit) {
    val strings = LocalVelroStrings.current
    FilterChip(
        selected = type.code == selected,
        onClick = { onEvent(VehicleEvent.TypeChanged(type.code)) },
        label = { Text(strings[type.nameKey]) },
        shape = FilterChipDefaults.shape,
    )
}

@Composable
private fun VehiclePapers(
    papers: VehicleChecklist,
    uploading: String?,
    onEvent: (VehicleEvent) -> Unit,
) {
    val strings = LocalVelroStrings.current
    val context = LocalContext.current
    // Saveable: the photo picker is another app, and this one can be destroyed
    // behind it. Held in `remember` the type came back null and the callback
    // returned silently, so a driver picked his vehicle permit and nothing at
    // all happened.
    var pendingType by rememberSaveable { mutableStateOf<String?>(null) }

    val picker = rememberLauncherForActivityResult(
        ActivityResultContracts.PickVisualMedia()
    ) { uri: Uri? ->
        val kind = pendingType
        pendingType = null
        if (uri == null || kind == null) return@rememberLauncherForActivityResult
        // Read here rather than in the repository: the data layer is given
        // bytes and never a content URI, so it stays free of Android.
        val bytes = runCatching {
            context.contentResolver.openInputStream(uri)?.use { it.readBytes() }
        }.getOrNull() ?: return@rememberLauncherForActivityResult
        val mime = context.contentResolver.getType(uri) ?: "image/jpeg"
        onEvent(VehicleEvent.PaperPicked(kind, bytes, mime))
    }

    Column(verticalArrangement = Arrangement.spacedBy(Spacing.sm)) {
        Text(
            strings["vehicle.documents.title"],
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
        )
        Text(
            strings["vehicle.documents.subtitle"],
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        for (kind in papers.required) {
            VehiclePaperRow(
                typeCode = kind,
                document = papers.currentFor(kind),
                uploading = uploading == kind,
                onPick = {
                    pendingType = kind
                    picker.launch(
                        PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)
                    )
                },
            )
        }
    }
}

@Composable
private fun VehiclePaperRow(
    typeCode: String,
    document: VehicleDocument?,
    uploading: Boolean,
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
                val (statusKey, colour) = when (document?.status) {
                    null -> "driver.documents.not_sent" to
                        MaterialTheme.colorScheme.onSurfaceVariant
                    DocumentStatus.VERIFIED -> "document.status.verified" to
                        MaterialTheme.colorScheme.primary
                    DocumentStatus.PENDING -> "document.status.pending" to
                        MaterialTheme.colorScheme.secondary
                    DocumentStatus.REJECTED -> "document.status.rejected" to
                        MaterialTheme.colorScheme.error
                    DocumentStatus.EXPIRED -> "document.status.expired" to
                        MaterialTheme.colorScheme.error
                }
                Text(
                    strings[statusKey],
                    style = MaterialTheme.typography.labelMedium,
                    color = colour,
                )
            }

            if (document?.rejectionReason != null) {
                Spacer(Modifier.height(Spacing.sm))
                // The reason is the whole point of showing this: a driver told
                // only "rejected" sends the same photograph again.
                Text(
                    document.rejectionReason!!,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.error,
                )
            }

            // The same expiry warning the driver's own documents carry, and for
            // the same reason: a permit that ran out stops the car, and being
            // told on the morning it happens is too late.
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
                enabled = !uploading,
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}
