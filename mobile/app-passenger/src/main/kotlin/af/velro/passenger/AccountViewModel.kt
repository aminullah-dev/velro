package af.velro.passenger

import af.velro.data.api.ApiResult
import af.velro.data.repository.AuthRepository
import af.velro.domain.Locale
import af.velro.domain.UserProfile
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class AccountUiState(
    val profile: UserProfile? = null,
    /** What is in the field, which is not what is saved until it is. */
    val draftName: String = "",
    val isSaving: Boolean = false,
    val saved: Boolean = false,
    val errorCode: String? = null,
    val errorContext: Map<String, Any?> = emptyMap(),
)

@HiltViewModel
class AccountViewModel @Inject constructor(
    private val auth: AuthRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(AccountUiState())
    val state: StateFlow<AccountUiState> = _state.asStateFlow()

    init { load() }

    private fun load() {
        viewModelScope.launch {
            when (val result = auth.profile()) {
                is ApiResult.Success -> _state.update {
                    it.copy(
                        profile = result.value,
                        // Only seeded from the server while the field is
                        // untouched, so a reload cannot overwrite what somebody
                        // is halfway through typing.
                        draftName = if (it.profile == null) {
                            result.value.fullName.orEmpty()
                        } else {
                            it.draftName
                        },
                    )
                }
                is ApiResult.Failure -> _state.update {
                    it.copy(errorCode = result.error.code, errorContext = result.error.context)
                }
            }
        }
    }

    fun onNameChanged(value: String) {
        _state.update { it.copy(draftName = value, saved = false, errorCode = null) }
    }

    fun saveName() {
        val name = _state.value.draftName.trim()
        _state.update { it.copy(isSaving = true, errorCode = null) }
        viewModelScope.launch {
            // Blank clears the name rather than storing an empty string --
            // the server already treats it that way, and a name that is a
            // space is neither a name nor an absence.
            when (val result = auth.updateName(name.ifBlank { null })) {
                is ApiResult.Success -> _state.update {
                    it.copy(profile = result.value, isSaving = false, saved = true)
                }
                is ApiResult.Failure -> _state.update {
                    it.copy(
                        isSaving = false,
                        errorCode = result.error.code,
                        errorContext = result.error.context,
                    )
                }
            }
        }
    }

    /**
     * Change the language of the whole app.
     *
     * The local write is what the app reads, so this takes effect on the next
     * frame whether or not the server is reachable -- which matters, because
     * somebody stuck in a language they cannot read is often the person with
     * the worst connection.
     */
    fun changeLocale(locale: Locale) {
        _state.update { it.copy(profile = it.profile?.copy(locale = locale)) }
        viewModelScope.launch { auth.changeLocale(locale) }
    }
}
