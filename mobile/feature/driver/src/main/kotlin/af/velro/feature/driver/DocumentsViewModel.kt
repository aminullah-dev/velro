package af.velro.feature.driver

import af.velro.data.api.ApiException
import af.velro.data.api.ApiResult
import af.velro.data.repository.DocumentRepository
import af.velro.domain.DocumentChecklist
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
 * The driver's own documents, section 27.
 *
 * This screen exists because "you cannot go online" is not an answer. It says
 * which document is missing, which was refused and why, and lets the driver fix
 * it without talking to anyone.
 */
data class DocumentsUiState(
    val checklist: DocumentChecklist? = null,
    val isLoading: Boolean = true,
    val uploadingType: String? = null,
    val errorCode: String? = null,
    val errorContext: Map<String, Any?> = emptyMap(),
    val justUploaded: String? = null,
) {
    val isUploading: Boolean get() = uploadingType != null
}

sealed interface DocumentsEvent {
    data object Refresh : DocumentsEvent
    data object RegisterAsDriver : DocumentsEvent
    data class Upload(
        val documentTypeCode: String,
        val bytes: ByteArray,
        val mimeType: String,
    ) : DocumentsEvent {
        // A ByteArray in a data class needs these, or two different photographs
        // compare equal whenever their references happen to match.
        override fun equals(other: Any?): Boolean =
            this === other ||
                (other is Upload &&
                    documentTypeCode == other.documentTypeCode &&
                    bytes.contentEquals(other.bytes) &&
                    mimeType == other.mimeType)

        override fun hashCode(): Int =
            (documentTypeCode.hashCode() * 31 + bytes.contentHashCode()) * 31 + mimeType.hashCode()
    }
    data object DismissError : DocumentsEvent
}

@HiltViewModel
class DocumentsViewModel @Inject constructor(
    private val documents: DocumentRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(DocumentsUiState())
    val state: StateFlow<DocumentsUiState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun onEvent(event: DocumentsEvent) {
        when (event) {
            DocumentsEvent.Refresh -> refresh()
            DocumentsEvent.RegisterAsDriver -> register()
            is DocumentsEvent.Upload -> upload(event)
            DocumentsEvent.DismissError -> _state.update { it.copy(errorCode = null) }
        }
    }

    private fun refresh() {
        _state.update { it.copy(isLoading = it.checklist == null, errorCode = null) }
        viewModelScope.launch {
            when (val result = documents.checklist()) {
                is ApiResult.Success ->
                    _state.update { it.copy(checklist = result.value, isLoading = false) }
                is ApiResult.Failure -> _state.update {
                    // Not yet a driver is not an error to alarm anyone with --
                    // it is the state before applying.
                    if (result.error.code == "DRIVER_NOT_FOUND") {
                        it.copy(isLoading = false, checklist = null, errorCode = null)
                    } else {
                        it.failed(result.error)
                    }
                }
            }
        }
    }

    private fun register() {
        _state.update { it.copy(isLoading = true, errorCode = null) }
        viewModelScope.launch {
            when (val result = documents.registerAsDriver()) {
                is ApiResult.Success -> refresh()
                is ApiResult.Failure -> _state.update { it.failed(result.error) }
            }
        }
    }

    private fun upload(event: DocumentsEvent.Upload) {
        if (_state.value.isUploading) return
        _state.update {
            it.copy(uploadingType = event.documentTypeCode, errorCode = null, justUploaded = null)
        }
        viewModelScope.launch {
            when (
                val result = documents.upload(
                    documentTypeCode = event.documentTypeCode,
                    bytes = event.bytes,
                    mimeType = event.mimeType,
                )
            ) {
                is ApiResult.Success -> {
                    _state.update {
                        it.copy(uploadingType = null, justUploaded = event.documentTypeCode)
                    }
                    refresh()
                }
                is ApiResult.Failure ->
                    _state.update { it.copy(uploadingType = null).failed(result.error) }
            }
        }
    }

    private fun DocumentsUiState.failed(error: ApiException) = copy(
        isLoading = false,
        uploadingType = null,
        errorCode = error.code,
        errorContext = error.context,
    )
}
