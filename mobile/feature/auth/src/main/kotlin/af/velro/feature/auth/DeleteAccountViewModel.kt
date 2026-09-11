package af.velro.feature.auth

import af.velro.data.api.ApiResult
import af.velro.data.repository.AuthRepository
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.getAndUpdate
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Where a deletion stands.
 *
 * The error is a code, as on every other screen: the screen resolves it in the
 * language being read, so a refusal that arrives after a language change is
 * not replayed in the old one.
 */
data class AccountDeletionState(
    val isDeleting: Boolean = false,
    /**
     * The server said yes, and this phone has already forgotten the account.
     *
     * Nothing on the deletion screen acts on it: clearing the session is what
     * takes the app to sign-in. It keeps the button spinning for the moment
     * in between, so the one tap that worked cannot be followed by a second
     * one on a screen that is on its way out.
     */
    val deleted: Boolean = false,
    val errorCode: String? = null,
    val errorContext: Map<String, Any?> = emptyMap(),
) {
    /** One request at a time, and none after the one that worked. */
    val canDelete: Boolean get() = !isDeleting && !deleted
}

/**
 * Asking the server to delete the account, exactly once per tap that means it.
 *
 * A plain class rather than the ViewModel itself, so a test can drive it with
 * a fake answer and no Android: the part worth proving is that a double tap
 * sends one request and that a refusal leaves the person where they were, and
 * neither needs a device to find out.
 */
class AccountDeletion(
    private val scope: CoroutineScope,
    private val delete: suspend () -> ApiResult<Unit>,
) {
    private val _state = MutableStateFlow(AccountDeletionState())
    val state: StateFlow<AccountDeletionState> = _state.asStateFlow()

    fun confirm() {
        // The button is disabled while this runs, but the guard lives here
        // too: a disabled button is a drawing, and the dialog's confirm can be
        // tapped twice in the frame before the dialog has gone. Checked and
        // claimed in one step, so two taps cannot both find it free.
        val before = _state.getAndUpdate {
            if (it.canDelete) {
                it.copy(isDeleting = true, errorCode = null, errorContext = emptyMap())
            } else {
                it
            }
        }
        if (!before.canDelete) return

        scope.launch {
            when (val result = delete()) {
                is ApiResult.Success -> _state.update {
                    it.copy(isDeleting = false, deleted = true)
                }
                is ApiResult.Failure -> _state.update {
                    it.copy(
                        isDeleting = false,
                        errorCode = result.error.code,
                        errorContext = result.error.context,
                    )
                }
            }
        }
    }
}

@HiltViewModel
class DeleteAccountViewModel @Inject constructor(
    private val auth: AuthRepository,
) : ViewModel() {

    private val deletion = AccountDeletion(viewModelScope, auth::deleteAccount)
    val state: StateFlow<AccountDeletionState> = deletion.state

    private val _holdsDriverRecords = MutableStateFlow(false)

    /**
     * Whether this account is a driver's as well.
     *
     * One account, one deletion, whichever app it is done from: a driver who
     * also books seats and deletes from the passenger app loses his papers
     * too, and the screen has to say so there as well.
     *
     * Read once, not observed. The roles are cleared with the session the
     * moment the deletion succeeds, and the sentence must not vanish from
     * under the person reading it.
     */
    val holdsDriverRecords: StateFlow<Boolean> = _holdsDriverRecords.asStateFlow()

    init {
        viewModelScope.launch {
            _holdsDriverRecords.value = DRIVER_ROLE in auth.roles.first()
        }
    }

    fun delete() = deletion.confirm()

    private companion object {
        /** The role `Session.isDriver` reads; the roles here are the same list. */
        const val DRIVER_ROLE = "DRIVER"
    }
}
