package af.velro.feature.driver

import af.velro.data.api.ApiException
import af.velro.data.api.ApiResult
import af.velro.data.repository.DocumentRepository
import af.velro.data.repository.VehicleRepository
import af.velro.domain.Vehicle
import af.velro.domain.VehicleChecklist
import af.velro.domain.VehicleType
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Vehicle registration, sections 26 and 52.
 *
 * The form is the same whether the driver has never registered a car or is
 * moving to a different one, because the driver is answering one question --
 * "which car am I driving?" -- and the server decides from the plate whether
 * that is an edit or a replacement.
 */
data class VehicleUiState(
    val vehicle: Vehicle? = null,
    /** The car's own papers -- جواز سیر. Null until a car exists to hold them. */
    val papers: VehicleChecklist? = null,
    val uploadingPaper: String? = null,
    val types: List<VehicleType> = emptyList(),
    val isLoading: Boolean = true,
    val isSaving: Boolean = false,
    val isEditing: Boolean = false,
    val saved: Boolean = false,
    val errorCode: String? = null,
    val errorContext: Map<String, Any?> = emptyMap(),
    // The form
    val typeCode: String = "",
    val plate: String = "",
    val seats: String = "",
    val brand: String = "",
    val model: String = "",
    val year: String = "",
    val colour: String = "",
) {
    val selectedType: VehicleType? get() = types.firstOrNull { it.code == typeCode }

    /**
     * Type and plate are the only fields that must be filled: the rest describe
     * the car for a passenger looking for it, and a driver standing at a station
     * should not be blocked from working over a missing colour.
     */
    val canSubmit: Boolean
        get() = !isSaving && typeCode.isNotBlank() && plate.trim().length >= 2 &&
            (seats.isBlank() || seats.toIntOrNull()?.let { it in 1..60 } == true) &&
            (year.isBlank() || year.toIntOrNull()?.let { it in 1950..2100 } == true)
}

sealed interface VehicleEvent {
    data object Refresh : VehicleEvent
    data class PaperPicked(
        val documentTypeCode: String,
        val bytes: ByteArray,
        val mimeType: String,
    ) : VehicleEvent {
        // ByteArray in a data class: equals/hashCode compare references, which
        // would make two different photographs of the same size look equal.
        // The event is consumed immediately and never compared, and spelling
        // this out is cheaper than a silent surprise later.
        override fun equals(other: Any?) = this === other
        override fun hashCode() = System.identityHashCode(this)
    }
    data object StartEditing : VehicleEvent
    data object CancelEditing : VehicleEvent
    data object Submit : VehicleEvent
    data class TypeChanged(val code: String) : VehicleEvent
    data class PlateChanged(val value: String) : VehicleEvent
    data class SeatsChanged(val value: String) : VehicleEvent
    data class BrandChanged(val value: String) : VehicleEvent
    data class ModelChanged(val value: String) : VehicleEvent
    data class YearChanged(val value: String) : VehicleEvent
    data class ColourChanged(val value: String) : VehicleEvent
}

@HiltViewModel
class VehicleViewModel @Inject constructor(
    private val vehicles: VehicleRepository,
    private val documents: DocumentRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(VehicleUiState())
    val state: StateFlow<VehicleUiState> = _state.asStateFlow()

    init { load() }

    fun onEvent(event: VehicleEvent) {
        when (event) {
            VehicleEvent.Refresh -> load()
            is VehicleEvent.PaperPicked -> uploadPaper(event)
            VehicleEvent.StartEditing -> _state.update { it.copy(isEditing = true, saved = false) }
            VehicleEvent.CancelEditing -> _state.update { it.formFrom(it.vehicle, editing = false) }
            VehicleEvent.Submit -> submit()
            is VehicleEvent.TypeChanged -> _state.update { current ->
                // Picking a type fills the seat count with that type's usual
                // capacity, but only while the driver has not set their own --
                // a Hiace with a row removed is still the driver's to state.
                val type = current.types.firstOrNull { it.code == event.code }
                val untouched = current.seats.isBlank() ||
                    current.seats == current.selectedType?.defaultSeatCapacity?.toString()
                current.copy(
                    typeCode = event.code,
                    seats = if (untouched) type?.defaultSeatCapacity?.toString() ?: current.seats
                    else current.seats,
                )
            }
            is VehicleEvent.PlateChanged -> _state.update { it.copy(plate = event.value) }
            is VehicleEvent.SeatsChanged -> _state.update { it.copy(seats = event.value.digits()) }
            is VehicleEvent.BrandChanged -> _state.update { it.copy(brand = event.value) }
            is VehicleEvent.ModelChanged -> _state.update { it.copy(model = event.value) }
            is VehicleEvent.YearChanged -> _state.update { it.copy(year = event.value.digits()) }
            is VehicleEvent.ColourChanged -> _state.update { it.copy(colour = event.value) }
        }
    }

    private fun load() {
        _state.update { it.copy(isLoading = true, errorCode = null) }
        viewModelScope.launch {
            // Types first: without them the picker has nothing to offer, so a
            // failure there is a failure of the whole screen.
            when (val types = vehicles.types()) {
                is ApiResult.Success -> {
                    val vehicle = (vehicles.current() as? ApiResult.Success)?.value
                    // The papers hang off the car, so there is nothing to ask
                    // for until one exists.
                    val papers = vehicle?.id?.let {
                        (documents.vehicleChecklist(it) as? ApiResult.Success)?.value
                    }
                    _state.update {
                        it.copy(types = types.value, isLoading = false, papers = papers)
                            .formFrom(vehicle, editing = vehicle == null)
                    }
                }
                is ApiResult.Failure -> _state.update { it.withError(types.error) }
            }
        }
    }

    private fun submit() {
        val s = _state.value
        if (!s.canSubmit) return
        _state.update { it.copy(isSaving = true, errorCode = null, saved = false) }
        viewModelScope.launch {
            val result = vehicles.register(
                vehicleTypeCode = s.typeCode,
                plateNumber = s.plate.trim(),
                seatCapacity = s.seats.toIntOrNull(),
                brand = s.brand,
                model = s.model,
                year = s.year.toIntOrNull(),
                colour = s.colour,
            )
            when (result) {
                is ApiResult.Success -> {
                    // Re-read rather than trust the form: the server canonicalises
                    // the plate and decides the status, and the driver should see
                    // what was actually stored.
                    val vehicle = (vehicles.current() as? ApiResult.Success)?.value
                    val papers = vehicle?.id?.let {
                        (documents.vehicleChecklist(it) as? ApiResult.Success)?.value
                    }
                    _state.update {
                        it.copy(isSaving = false, saved = true, papers = papers)
                            .formFrom(vehicle, editing = false)
                    }
                }
                is ApiResult.Failure ->
                    _state.update { it.copy(isSaving = false).withError(result.error) }
            }
        }
    }

    private fun uploadPaper(event: VehicleEvent.PaperPicked) {
        val vehicleId = _state.value.vehicle?.id ?: return
        _state.update {
            it.copy(uploadingPaper = event.documentTypeCode, errorCode = null)
        }
        viewModelScope.launch {
            when (
                val result = documents.uploadForVehicle(
                    vehicleId, event.documentTypeCode, event.bytes, event.mimeType,
                )
            ) {
                is ApiResult.Success -> {
                    // Re-read: sending a new permit takes the car out of
                    // service until someone reviews it, and the driver has to
                    // see that rather than assume they are still on the road.
                    val papers =
                        (documents.vehicleChecklist(vehicleId) as? ApiResult.Success)?.value
                    val vehicle = (vehicles.current() as? ApiResult.Success)?.value
                    _state.update {
                        it.copy(uploadingPaper = null, papers = papers, vehicle = vehicle)
                    }
                }
                is ApiResult.Failure -> _state.update {
                    it.copy(uploadingPaper = null).withError(result.error)
                }
            }
        }
    }
}

private fun String.digits() = filter { it.isDigit() }

private fun VehicleUiState.withError(error: ApiException) = copy(
    isLoading = false,
    isSaving = false,
    errorCode = error.code,
    errorContext = error.context,
)

private fun VehicleUiState.formFrom(vehicle: Vehicle?, editing: Boolean) = copy(
    vehicle = vehicle,
    isEditing = editing,
    errorCode = null,
    typeCode = vehicle?.vehicleTypeCode ?: typeCode,
    plate = vehicle?.plateNumber ?: "",
    seats = vehicle?.seatCapacity?.toString() ?: "",
    brand = vehicle?.brand ?: "",
    model = vehicle?.model ?: "",
    year = vehicle?.year?.toString() ?: "",
    colour = vehicle?.colour ?: "",
)
