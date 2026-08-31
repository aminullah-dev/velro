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
    /**
     * A refresh the driver pulled for.
     *
     * This screen is the one he returns to while waiting for the office to
     * approve his licence, and approval is what lets him work at all -- so
     * "check again" is the reason to be here, and it had no control.
     */
    val isRefreshing: Boolean = false,
    val uploadingType: String? = null,
    /**
     * Thumbnails of what he actually sent, by document id.
     *
     * The screen listed three documents by name and status and showed none of
     * them. A driver who photographed the wrong page of his licence -- or his
     * thumb -- had no way to discover it: the app said "sent, approved" about
     * an image he could not see, and the only correction available was to send
     * another and hope.
     *
     * A map rather than a field on the document, because these arrive one at a
     * time and after the list does. An absent entry means "not fetched yet",
     * which the screen draws as a placeholder rather than as an error -- a
     * thumbnail that failed is not worth an error over, and the status beside
     * it is the load-bearing information.
     */
    val thumbnails: Map<String, ByteArray> = emptyMap(),
    val errorCode: String? = null,
    val errorContext: Map<String, Any?> = emptyMap(),
    val justUploaded: String? = null,
    /**
     * Kept in state rather than sent and forgotten.
     *
     * A refused request rolls back everything it wrote -- one session per
     * request on the server -- so a name that went out with a rejected
     * registration was never stored. Holding it here means he is not asked to
     * type it a second time on a phone he is holding one-handed.
     */
    val typedName: String = "",
) {
    val isUploading: Boolean get() = uploadingType != null
}

sealed interface DocumentsEvent {
    data object Refresh : DocumentsEvent

    /** The same read, without blanking the list behind a spinner. */
    data object PullToRefresh : DocumentsEvent
    data object RegisterAsDriver : DocumentsEvent
    data class NameChanged(val value: String) : DocumentsEvent
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
            DocumentsEvent.PullToRefresh -> refresh(pulled = true)
            DocumentsEvent.RegisterAsDriver -> register()
            is DocumentsEvent.NameChanged ->
                // 160 is the column, so the field cannot outgrow the row.
                _state.update { it.copy(typedName = event.value.take(160)) }
            is DocumentsEvent.Upload -> upload(event)
            DocumentsEvent.DismissError -> _state.update { it.copy(errorCode = null) }
        }
    }

    /**
     * Fetch the images behind the list, after the list.
     *
     * Never awaited by the checklist load: the names and statuses are what the
     * screen is for, and three image downloads on a Ghorband connection must
     * not hold them back. Each lands on its own as it arrives.
     *
     * Only documents that are current, and only those not already held --
     * re-fetching on every pull would spend a driver's data to redraw pictures
     * he is already looking at.
     */
    private fun loadThumbnails(checklist: DocumentChecklist) {
        val wanted = checklist.documents
            .filter { it.isCurrent && it.id !in _state.value.thumbnails }
        for (document in wanted) {
            viewModelScope.launch {
                (documents.file(document.id) as? ApiResult.Success)?.let { result ->
                    _state.update { it.copy(thumbnails = it.thumbnails + (document.id to result.value)) }
                }
                // A failure is silent on purpose. The document's status is the
                // thing this screen owes the driver; a missing picture beside
                // a correct "approved" is a smaller problem than an error
                // banner that makes him think his licence was refused.
            }
        }
    }

    private fun refresh(pulled: Boolean = false) {
        _state.update {
            it.copy(
                isLoading = !pulled && it.checklist == null,
                isRefreshing = pulled,
                errorCode = null,
            )
        }
        viewModelScope.launch {
            when (val result = documents.checklist()) {
                is ApiResult.Success -> {
                    _state.update { it.copy(checklist = result.value, isLoading = false) }
                    loadThumbnails(result.value)
                }
                is ApiResult.Failure -> _state.update {
                    // Not yet a driver is not an error to alarm anyone with --
                    // it is the state before applying.
                    //
                    // PERMISSION_DENIED as well as DRIVER_NOT_FOUND: this
                    // endpoint sits behind require_driver, so somebody who has
                    // never applied is refused by the guard and never reaches
                    // the DRIVER_NOT_FOUND inside it. Only checking the inner
                    // code meant the apply screen carried a red "you do not
                    // have permission to do this" above its own Apply button.
                    if (result.error.code == "DRIVER_NOT_FOUND" ||
                        result.error.code == "PERMISSION_DENIED"
                    ) {
                        it.copy(isLoading = false, checklist = null, errorCode = null)
                    } else {
                        it.failed(result.error)
                    }
                }
            }
            // Cleared whichever way the read went, or a driver with no
            // signal keeps a spinning indicator until he leaves the screen.
            _state.update { it.copy(isRefreshing = false) }
        }
    }

    private fun register() {
        _state.update { it.copy(isLoading = true, errorCode = null) }
        viewModelScope.launch {
            when (val result = documents.registerAsDriver(
                fullName = _state.value.typedName.trim().ifEmpty { null },
            )) {
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
