package af.velro.feature.safety

import af.velro.data.api.ApiResult
import af.velro.data.repository.SafetyRepository
import af.velro.domain.SupportTicket
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ReportsUiState(
    val reports: List<SupportTicket> = emptyList(),
    val openId: String? = null,
    val draft: String = "",
    val isLoading: Boolean = true,
    val isSending: Boolean = false,
    val errorCode: String? = null,
    val errorContext: Map<String, Any?> = emptyMap(),
    val replyErrorCode: String? = null,
)

sealed interface ReportsEvent {
    data object Refresh : ReportsEvent
    data class Toggle(val id: String) : ReportsEvent
    data class DraftChanged(val text: String) : ReportsEvent
    data class Send(val id: String) : ReportsEvent
}

@HiltViewModel
class ReportsViewModel @Inject constructor(
    private val safety: SafetyRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(ReportsUiState())
    val state: StateFlow<ReportsUiState> = _state.asStateFlow()

    init { load() }

    fun onEvent(event: ReportsEvent) {
        when (event) {
            ReportsEvent.Refresh -> load()
            is ReportsEvent.Toggle -> _state.update {
                // Opening a different report drops the draft with it: sending
                // words typed under one reference into another is worse than
                // losing them.
                val opening = if (it.openId == event.id) null else event.id
                it.copy(openId = opening, draft = "", replyErrorCode = null)
            }
            is ReportsEvent.DraftChanged -> _state.update {
                it.copy(draft = event.text, replyErrorCode = null)
            }
            is ReportsEvent.Send -> send(event.id)
        }
    }

    private fun load() {
        _state.update { it.copy(isLoading = true, errorCode = null) }
        viewModelScope.launch {
            when (val result = safety.myReports()) {
                is ApiResult.Success -> _state.update {
                    it.copy(reports = result.value, isLoading = false)
                }
                is ApiResult.Failure -> _state.update {
                    it.copy(
                        isLoading = false,
                        errorCode = result.error.code,
                        errorContext = result.error.context,
                    )
                }
            }
        }
    }

    private fun send(id: String) {
        val body = _state.value.draft.trim()
        if (body.isEmpty() || _state.value.isSending) return
        _state.update { it.copy(isSending = true, replyErrorCode = null) }
        viewModelScope.launch {
            when (val result = safety.reply(id, body)) {
                is ApiResult.Success -> {
                    // Re-read rather than append locally: a reply from the
                    // person who raised it pulls a resolved report back open,
                    // and the server is what decides that.
                    val refreshed = (safety.myReports() as? ApiResult.Success)?.value
                    _state.update { current ->
                        current.copy(
                            isSending = false,
                            draft = "",
                            reports = refreshed ?: current.reports,
                        )
                    }
                }
                is ApiResult.Failure -> _state.update {
                    it.copy(isSending = false, replyErrorCode = result.error.code)
                }
            }
        }
    }
}
