package af.velro.feature.safety

import af.velro.data.api.ApiResult
import af.velro.data.repository.SafetyRepository
import af.velro.domain.SafetyContacts
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/** The report form, which only exists once somebody asks for it. */
data class ReportUiState(
    val categoryCode: String? = null,
    val body: String = "",
    val isSending: Boolean = false,
    val reference: String? = null,
    val errorCode: String? = null,
    val errorContext: Map<String, Any?> = emptyMap(),
) {
    val canSubmit: Boolean
        get() = !isSending && categoryCode != null && body.trim().length >= 3
}

data class HelpUiState(
    /**
     * Never null and never empty.
     *
     * The sheet has no loading state on purpose: it opens with the built-in
     * numbers already in hand, and a spinner where 119 should be is the one
     * thing this screen must never show.
     */
    val contacts: SafetyContacts = SafetyContacts.BUILT_IN,
    /** Null until the person presses the report door. */
    val report: ReportUiState? = null,
    /**
     * The reference of the last report sent from this screen.
     *
     * Held outside the form because the form's only button used to destroy it:
     * a person read TKT-2026-000042, pressed Close, and it was gone. It is the
     * one thing they keep, and the thing an operator asks for on the phone.
     */
    val lastReference: String? = null,
)

@HiltViewModel
class HelpViewModel @Inject constructor(
    private val safety: SafetyRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(HelpUiState())
    val state: StateFlow<HelpUiState> = _state.asStateFlow()

    fun openReport() = _state.update { it.copy(report = ReportUiState()) }

    fun closeReport() = _state.update { it.copy(report = null) }

    fun chooseCategory(code: String) = _state.update {
        it.copy(
            report = (it.report ?: ReportUiState()).copy(categoryCode = code, errorCode = null)
        )
    }

    fun changeBody(text: String) = _state.update {
        it.copy(report = (it.report ?: ReportUiState()).copy(body = text, errorCode = null))
    }

    /**
     * Send it, with the ride attached when there is one.
     *
     * The reference comes back and is shown; it is the only thing the person
     * keeps, and it has to survive the screen closing.
     */
    fun submitReport(tripId: String?, bookingId: String?) {
        val report = _state.value.report ?: return
        if (!report.canSubmit) return
        _state.update { it.copy(report = report.copy(isSending = true, errorCode = null)) }
        viewModelScope.launch {
            when (
                val result = safety.report(
                    categoryCode = report.categoryCode!!,
                    body = report.body.trim(),
                    tripId = tripId,
                    bookingId = bookingId,
                )
            ) {
                // `it.report`, never the `report` captured before the
                // request. Copying the captured value discards anything typed
                // while the request was in flight -- the same shape of mistake
                // as reading rows before an UPDATE and using them after it.
                is ApiResult.Success -> _state.update { current ->
                    current.copy(
                        report = (current.report ?: report).copy(
                            isSending = false,
                            reference = result.value,
                        ),
                        // Kept outside the form, so closing it cannot erase the
                        // one thing the person has to hold on to.
                        lastReference = result.value,
                    )
                }
                is ApiResult.Failure -> _state.update { current ->
                    current.copy(
                        report = (current.report ?: report).copy(
                            isSending = false,
                            errorCode = result.error.code,
                            errorContext = result.error.context,
                        )
                    )
                }
            }
        }
    }

    init {
        viewModelScope.launch {
            // Read the cache first -- instant, no network.
            _state.update { it.copy(contacts = safety.contacts()) }
            // Then refresh, best effort, for the next time the sheet opens.
            // Never awaited before rendering: a person holding this screen is
            // not waiting on a request.
            safety.refreshContacts()
            _state.update { it.copy(contacts = safety.contacts()) }
        }
    }
}
