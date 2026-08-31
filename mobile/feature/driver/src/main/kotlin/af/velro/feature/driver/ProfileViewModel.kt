package af.velro.feature.driver

import af.velro.data.api.ApiResult
import af.velro.data.repository.DocumentRepository
import af.velro.data.repository.DriverRepository
import af.velro.domain.DriverProfile
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class ProfileUiState(
    val profile: DriverProfile? = null,
    /**
     * The driver's face, if he has sent one.
     *
     * Separate from [profile] because it comes from a different endpoint and
     * arrives later: the profile is the screen, and a photograph that is slow
     * or missing must not hold back his name, his rating or his car.
     */
    val photo: ByteArray? = null,
    val isLoading: Boolean = true,
    val isRefreshing: Boolean = false,
    val errorCode: String? = null,
    val errorContext: Map<String, Any?> = emptyMap(),
)

sealed interface ProfileEvent {
    data object Refresh : ProfileEvent
    data object PullToRefresh : ProfileEvent
}

@HiltViewModel
class ProfileViewModel @Inject constructor(
    private val drivers: DriverRepository,
    private val documents: DocumentRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(ProfileUiState())
    val state: StateFlow<ProfileUiState> = _state.asStateFlow()

    init { load() }

    fun onEvent(event: ProfileEvent) {
        when (event) {
            ProfileEvent.Refresh -> load()
            ProfileEvent.PullToRefresh -> load(pulled = true)
        }
    }

    private fun load(pulled: Boolean = false) {
        _state.update {
            it.copy(
                isLoading = !pulled && it.profile == null,
                isRefreshing = pulled,
                errorCode = null,
            )
        }
        viewModelScope.launch {
            when (val result = drivers.profile()) {
                is ApiResult.Success -> {
                    _state.update { it.copy(profile = result.value, isLoading = false) }
                    loadPhoto()
                }
                is ApiResult.Failure -> _state.update {
                    it.copy(
                        isLoading = false,
                        errorCode = result.error.code,
                        errorContext = result.error.context,
                    )
                }
            }
            _state.update { it.copy(isRefreshing = false) }
        }
    }

    /**
     * His selfie, from the documents he already sent.
     *
     * There is no separate avatar to upload: the identity photograph the
     * office approved him on is the picture of him the product has, and asking
     * for a second one would be asking twice for the same thing.
     *
     * Silent on failure, and skipped once held. A profile without a face is a
     * profile; an error banner over a missing picture is noise on the screen a
     * driver opens to check his standing.
     */
    private suspend fun loadPhoto() {
        if (_state.value.photo != null) return
        val checklist = (documents.checklist() as? ApiResult.Success)?.value ?: return
        val selfie = checklist.documents.firstOrNull {
            it.isCurrent && it.documentTypeCode == SELFIE
        } ?: return
        (documents.file(selfie.id) as? ApiResult.Success)?.let { bytes ->
            _state.update { it.copy(photo = bytes.value) }
        }
    }

    private companion object {
        /** The document type that is a picture of the driver himself. */
        const val SELFIE = "SELFIE"
    }
}
