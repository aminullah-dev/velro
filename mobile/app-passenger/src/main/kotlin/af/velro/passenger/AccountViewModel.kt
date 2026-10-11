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
    /**
     * What is in the two fields, which is not what is saved until it is.
     *
     * Two since the owner made both parts required (2026-10-10). The server
     * still keeps one full_name; these are split from it on load and joined
     * back on save -- see PersonName.
     */
    val draftFirst: String = "",
    val draftLast: String = "",
    val isSaving: Boolean = false,
    val saved: Boolean = false,
    val errorCode: String? = null,
    val errorContext: Map<String, Any?> = emptyMap(),
) {
    /**
     * Save is offered only for a change that would be accepted: both parts
     * long enough, and different from what is stored. A name cannot be
     * cleared any more -- it is required -- so there is no blank to save.
     */
    val canSave: Boolean
        get() = !isSaving &&
            PersonName.isValid(draftFirst, draftLast) &&
            PersonName.join(draftFirst, draftLast) != profile?.fullName?.trim()
}

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
                        draftFirst = if (it.profile == null) {
                            PersonName.split(result.value.fullName).first
                        } else {
                            it.draftFirst
                        },
                        draftLast = if (it.profile == null) {
                            PersonName.split(result.value.fullName).second
                        } else {
                            it.draftLast
                        },
                    )
                }
                is ApiResult.Failure -> _state.update {
                    it.copy(errorCode = result.error.code, errorContext = result.error.context)
                }
            }
        }
    }

    fun onFirstNameChanged(value: String) {
        _state.update { it.copy(draftFirst = value, saved = false, errorCode = null) }
    }

    fun onLastNameChanged(value: String) {
        _state.update { it.copy(draftLast = value, saved = false, errorCode = null) }
    }

    fun saveName() {
        val current = _state.value
        // The button is disabled for this already; the guard is here too,
        // because a disabled button is a drawing and this is the call.
        if (!current.canSave) return
        _state.update { it.copy(isSaving = true, errorCode = null) }
        viewModelScope.launch {
            when (val result = auth.updateName(PersonName.join(current.draftFirst, current.draftLast))) {
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
