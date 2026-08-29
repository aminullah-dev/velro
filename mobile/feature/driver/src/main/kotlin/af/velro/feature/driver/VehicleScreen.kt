package af.velro.feature.driver

import af.velro.core.i18n.Numerals
import af.velro.core.ui.component.ErrorState
import af.velro.core.ui.component.InlineError
import af.velro.core.ui.component.LoadingState
import af.velro.core.ui.component.PrimaryAction
import af.velro.core.ui.component.SecondaryAction
import af.velro.core.ui.component.VelroCard
import af.velro.core.ui.theme.LocalVelroStrings
import af.velro.core.ui.theme.Spacing
import af.velro.domain.Vehicle
import af.velro.domain.VehicleStatus
import af.velro.domain.VehicleType
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.foundation.text.KeyboardOptions
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle

@Composable
fun VehicleRoute(viewModel: VehicleViewModel = hiltViewModel()) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    VehicleScreen(state, viewModel::onEvent)
}

@Composable
fun VehicleScreen(
    state: VehicleUiState,
    onEvent: (VehicleEvent) -> Unit,
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

    Column(
        modifier
            .fillMaxSize()
            .statusBarsPadding()
            .verticalScroll(rememberScrollState())
            .padding(Spacing.lg),
        verticalArrangement = Arrangement.spacedBy(Spacing.md),
    ) {
        Text(
            strings["driver.vehicle.title"],
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.SemiBold,
        )

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
