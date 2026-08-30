package af.velro.feature.auth

import af.velro.data.api.ApiException
import af.velro.data.api.ApiResult
import af.velro.data.repository.AuthRepository
import af.velro.domain.Locale
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.receiveAsFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

/**
 * Sign-in state.
 *
 * One immutable object per screen. The error is an *code*, never a rendered
 * string: the composable resolves it in the locale being read, and a state
 * object holding a sentence would replay the wrong language after a locale
 * change.
 */
data class SignInUiState(
    val step: Step = Step.PHONE,
    val phone: String = "",
    val code: String = "",
    val locale: Locale = Locale.DARI,
    val isSubmitting: Boolean = false,
    val errorCode: String? = null,
    val errorContext: Map<String, Any?> = emptyMap(),
    /**
     * Seconds left before another code may be asked for.
     *
     * The server sends this with every accepted request and enforces its own
     * limit regardless (3 per 60s, `otp.max_per_window`). Counting it down here
     * is not the security control -- it is the cost control. Every send is a
     * real SMS at about $0.45 against a ~$50/month budget, so a person who taps
     * "send again" three times because nothing arrived yet has spent $1.35, and
     * the third tap earns a rate-limit error they cannot interpret. Showing the
     * wait turns all three into one.
     */
    val resendAfterSeconds: Int = 0,
    /** Development builds echo the code so a developer with no SMS gateway can sign in. */
    val debugCode: String? = null,
) {
    enum class Step { PHONE, CODE }

    val canSubmitPhone: Boolean get() = phone.filter(Char::isDigit).length >= 9 && !isSubmitting
    val canSubmitCode: Boolean get() = code.length >= 4 && !isSubmitting
    val canResend: Boolean get() = resendAfterSeconds <= 0 && !isSubmitting
}

sealed interface SignInEvent {
    data class PhoneChanged(val value: String) : SignInEvent
    data class CodeChanged(val value: String) : SignInEvent
    data class LocaleChanged(val locale: Locale) : SignInEvent
    data object RequestCode : SignInEvent
    data object SubmitCode : SignInEvent
    data object Back : SignInEvent
    data object DismissError : SignInEvent
}

/** One-shot outcomes. Navigation goes through a channel, never through state:
 *  state replays on rotation, and a replayed navigation is a bug. */
sealed interface SignInEffect {
    data class SignedIn(val isDriver: Boolean, val isNewUser: Boolean) : SignInEffect
}

@HiltViewModel
class SignInViewModel @Inject constructor(
    private val auth: AuthRepository,
) : ViewModel() {

    private val _state = MutableStateFlow(SignInUiState())
    val state: StateFlow<SignInUiState> = _state.asStateFlow()

    private val _effects = Channel<SignInEffect>(Channel.BUFFERED)
    val effects = _effects.receiveAsFlow()

    fun onEvent(event: SignInEvent) {
        when (event) {
            is SignInEvent.PhoneChanged ->
                _state.update { it.copy(phone = event.value, errorCode = null) }

            is SignInEvent.CodeChanged ->
                _state.update { it.copy(code = event.value.take(8), errorCode = null) }

            is SignInEvent.LocaleChanged -> {
                _state.update { it.copy(locale = event.locale) }
                viewModelScope.launch { auth.setLocale(event.locale) }
            }

            SignInEvent.RequestCode -> requestCode()
            SignInEvent.SubmitCode -> submitCode()

            SignInEvent.Back ->
                _state.update {
                    it.copy(step = SignInUiState.Step.PHONE, code = "", errorCode = null)
                }

            SignInEvent.DismissError -> _state.update { it.copy(errorCode = null) }
        }
    }

    private fun requestCode() {
        val current = _state.value
        if (!current.canSubmitPhone) return
        // The resend button is disabled while the clock runs, but the guard
        // lives here too: a disabled button is a drawing, and this is the only
        // place that spends money.
        if (current.step == SignInUiState.Step.CODE && !current.canResend) return

        _state.update { it.copy(isSubmitting = true, errorCode = null) }
        viewModelScope.launch {
            when (val result = auth.requestOtp(current.phone, current.locale)) {
                is ApiResult.Success -> _state.update {
                    it.copy(
                        step = SignInUiState.Step.CODE,
                        isSubmitting = false,
                        resendAfterSeconds = result.value.resend_after_seconds,
                        debugCode = result.value.debug_code,
                        // Prefilled in development only; in production this is
                        // null and the field starts empty.
                        code = result.value.debug_code.orEmpty(),
                    )
                }
                is ApiResult.Failure -> _state.update { it.failed(result.error) }
            }
            startResendCountdown()
        }
    }

    private var countdown: Job? = null

    /**
     * Tick the resend clock down to zero.
     *
     * In the ViewModel rather than the composable so it keeps running across a
     * rotation -- a countdown that restarts when the screen turns would hand
     * back the button early, which is the one thing it exists to prevent.
     */
    private fun startResendCountdown() {
        countdown?.cancel()
        countdown = viewModelScope.launch {
            while (_state.value.resendAfterSeconds > 0) {
                delay(1_000)
                _state.update { it.copy(resendAfterSeconds = it.resendAfterSeconds - 1) }
            }
        }
    }

    private fun submitCode() {
        val current = _state.value
        if (!current.canSubmitCode) return

        _state.update { it.copy(isSubmitting = true, errorCode = null) }
        viewModelScope.launch {
            when (val result = auth.verifyOtp(current.phone, current.code, current.locale)) {
                is ApiResult.Success -> {
                    _state.update { it.copy(isSubmitting = false) }
                    _effects.send(
                        SignInEffect.SignedIn(
                            isDriver = result.value.isDriver,
                            isNewUser = result.value.isNewUser,
                        )
                    )
                }
                is ApiResult.Failure -> _state.update { it.failed(result.error) }
            }
        }
    }

    private fun SignInUiState.failed(error: ApiException) = copy(
        isSubmitting = false,
        errorCode = error.code,
        errorContext = error.context,
        // A wrong code should clear the field; an expired one should send the
        // person back to ask for a new code rather than retyping into a dead one.
        code = if (error.code == "OTP_INVALID") "" else code,
        step = if (error.code == "OTP_EXPIRED") SignInUiState.Step.PHONE else step,
    )
}
