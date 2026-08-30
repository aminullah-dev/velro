package af.velro.feature.auth

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The resend clock.
 *
 * This is a cost control, not a security control -- the server enforces its own
 * limit either way (3 per 60s). It exists because every send is a real SMS at
 * about $0.45 against a ~$50/month budget, and the natural thing to do when no
 * message has arrived after ten seconds is to press the button again. Three
 * presses is $1.35 and a rate-limit error the person cannot interpret.
 *
 * `canResend` is the single predicate behind both the button's enabled state
 * and the guard inside requestCode(), so it is the thing worth pinning down.
 */
class ResendCooldownTest {

    private fun onCodeStep(seconds: Int, submitting: Boolean = false) =
        SignInUiState(
            step = SignInUiState.Step.CODE,
            phone = "0793817977",
            resendAfterSeconds = seconds,
            isSubmitting = submitting,
        )

    @Test
    fun `a fresh code cannot immediately be asked for again`() {
        assertFalse(onCodeStep(seconds = 60).canResend)
    }

    @Test
    fun `the last second of the wait is still a wait`() {
        // The off-by-one that would hand the button back early.
        assertFalse(onCodeStep(seconds = 1).canResend)
    }

    @Test
    fun `the button comes back when the clock reaches zero`() {
        assertTrue(onCodeStep(seconds = 0).canResend)
    }

    @Test
    fun `a clock that overshoots below zero does not lock the button forever`() {
        assertTrue(onCodeStep(seconds = -1).canResend)
    }

    @Test
    fun `a request already in flight does not accept a second one`() {
        // Double-tap on a slow valley connection: the first send is still open,
        // the clock has not been set yet, and without this both go out.
        assertFalse(onCodeStep(seconds = 0, submitting = true).canResend)
    }
}
