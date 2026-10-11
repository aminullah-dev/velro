package af.velro.passenger

import af.velro.data.api.ApiResult
import af.velro.data.repository.AuthRepository
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Whether the signed-in passenger still has to give a name.
 *
 * Decided in two steps. First from what the session already knows, which is a
 * local read of a few milliseconds: an account known to have a name goes home,
 * and an account this very sign-in created goes straight to the name step --
 * no frame of home first, no network. Then, for anybody else, from the
 * profile, quietly, with home already drawn: a launch with no signal must open
 * on her bookings, not on a spinner waiting for a profile that cannot arrive.
 * Only a profile that actually comes back without both parts of a name sends
 * her to the step;
 * a failure leaves her where she is and the question is asked next launch.
 *
 * Once a profile has shown a name the answer is kept with the session (see
 * AuthRepository.hasName), so it is not asked again until somebody signs out.
 */
@HiltViewModel
class NameGateViewModel @Inject constructor(
    private val auth: AuthRepository,
) : ViewModel() {

    private val _needsName = MutableStateFlow<Boolean?>(null)

    /** Null while the session is read; then whether the name step is due. */
    val needsName: StateFlow<Boolean?> = _needsName.asStateFlow()

    init {
        viewModelScope.launch {
            when {
                auth.hasName.first() -> _needsName.value = false
                auth.nameNeeded.first() -> _needsName.value = true
                else -> {
                    _needsName.value = false
                    val profile = (auth.profile() as? ApiResult.Success)?.value ?: return@launch
                    if (!PersonName.isFullName(profile.fullName)) {
                        _needsName.value = true
                    } else {
                        auth.rememberNamed()
                    }
                }
            }
        }
    }

    /** Saved: the name step gives way to home. */
    fun nameGiven() {
        _needsName.value = false
    }
}

data class NameUiState(
    val first: String = "",
    val last: String = "",
    val isSaving: Boolean = false,
    /**
     * Continue was asked for with a part still too short -- from the
     * keyboard's Done, since the button itself waits until both are valid.
     */
    val showRequired: Boolean = false,
    val errorCode: String? = null,
    val errorContext: Map<String, Any?> = emptyMap(),
) {
    val canContinue: Boolean get() = PersonName.isValid(first, last) && !isSaving
}

/** One-shot outcomes. Navigation goes through a channel, never through state. */
sealed interface NameEffect {
    data object Saved : NameEffect
}

/**
 * The name step: a first and a last name, both required, saved as one.
 *
 * Saved through the same profile call the account screen uses; nothing on the
 * server changed for this. Nothing is remembered locally until the server has
 * the name, so a save that fails asks again rather than letting her through
 * with no name a driver can read.
 */
@HiltViewModel
class NameViewModel @Inject constructor(
    private val auth: AuthRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(NameUiState())
    val state: StateFlow<NameUiState> = _state.asStateFlow()

    private val _effects = Channel<NameEffect>(Channel.BUFFERED)
    val effects = _effects.receiveAsFlow()

    fun onFirstChanged(value: String) {
        _state.update { it.copy(first = value, errorCode = null, showRequired = false) }
    }

    fun onLastChanged(value: String) {
        _state.update { it.copy(last = value, errorCode = null, showRequired = false) }
    }

    fun submit() {
        val current = _state.value
        if (current.isSaving) return
        if (!PersonName.isValid(current.first, current.last)) {
            _state.update { it.copy(showRequired = true) }
            return
        }
        _state.update { it.copy(isSaving = true, errorCode = null) }
        viewModelScope.launch {
            when (val result = auth.updateName(PersonName.join(current.first, current.last))) {
                is ApiResult.Success -> {
                    _state.update { it.copy(isSaving = false) }
                    _effects.send(NameEffect.Saved)
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
}
