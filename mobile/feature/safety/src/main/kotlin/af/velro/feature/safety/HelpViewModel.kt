package af.velro.feature.safety

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

data class HelpUiState(
    /**
     * Never null and never empty.
     *
     * The sheet has no loading state on purpose: it opens with the built-in
     * numbers already in hand, and a spinner where 119 should be is the one
     * thing this screen must never show.
     */
    val contacts: SafetyContacts = SafetyContacts.BUILT_IN,
)

@HiltViewModel
class HelpViewModel @Inject constructor(
    private val safety: SafetyRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(HelpUiState())
    val state: StateFlow<HelpUiState> = _state.asStateFlow()

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
