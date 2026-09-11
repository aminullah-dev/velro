package af.velro.feature.auth

import af.velro.data.api.ApiException
import af.velro.data.api.ApiResult
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The deletion screen's one decision: whether a tap becomes a request.
 *
 * [AccountDeletion] is what DeleteAccountViewModel delegates to, driven here
 * with a fake answer in place of the repository -- which needs a database and
 * a token store to construct, and whose own half (the phone forgetting the
 * account) is proved on a device by DeleteAccountTest in :data.
 *
 * Two properties matter. A refusal must leave the person exactly where they
 * were, with the reason on screen and the button back: a seat still booked is
 * a reason to go and cancel it, not the end of the road. And a second tap --
 * the dialog's confirm pressed twice on a slow valley connection, which is the
 * ordinary way anything gets sent twice here -- must send nothing.
 */
@OptIn(ExperimentalCoroutinesApi::class) // runCurrent, to hold a request in flight
class AccountDeletionTest {

    private fun refusal(code: String, status: Int) =
        ApiResult.Failure(ApiException(code, httpStatus = status))

    private fun TestScope.deletionAnswering(answer: suspend () -> ApiResult<Unit>): Pair<AccountDeletion, () -> Int> {
        var calls = 0
        val deletion = AccountDeletion(this) {
            calls++
            answer()
        }
        return deletion to { calls }
    }

    @Test
    fun `a yes is remembered and the button stays down`() = runTest {
        val (deletion, calls) = deletionAnswering { ApiResult.Success(Unit) }

        deletion.confirm()
        runCurrent()

        val state = deletion.state.value
        assertEquals(1, calls())
        assertTrue("the screen must know it worked", state.deleted)
        assertFalse(state.isDeleting)
        assertNull(state.errorCode)
        // The session is already gone and the app is on its way to sign-in;
        // a button that came back up here would send a request with no token.
        assertFalse(state.canDelete)
    }

    @Test
    fun `nothing is sent after the one that worked`() = runTest {
        val (deletion, calls) = deletionAnswering { ApiResult.Success(Unit) }

        deletion.confirm()
        runCurrent()
        deletion.confirm()
        runCurrent()

        assertEquals(1, calls())
    }

    @Test
    fun `each refusal keeps the account and says why`() = runTest {
        // The three the server can give, each something the person can act on.
        val refusals = listOf(
            "ACCOUNT_HAS_ACTIVE_BOOKING" to 409,
            "ACCOUNT_HAS_ACTIVE_TRIP" to 409,
            "ACCOUNT_STAFF_UNDELETABLE" to 403,
        )
        for ((code, status) in refusals) {
            val (deletion, calls) = deletionAnswering { refusal(code, status) }

            deletion.confirm()
            runCurrent()

            val state = deletion.state.value
            assertEquals(1, calls())
            assertEquals("$code must reach the screen as itself", code, state.errorCode)
            assertFalse("$code is not a deletion", state.deleted)
            assertFalse(state.isDeleting)
            assertTrue("after $code the button must come back", state.canDelete)
        }
    }

    @Test
    fun `a refusal can be tried again once it is dealt with`() = runTest {
        var answer: ApiResult<Unit> = refusal("ACCOUNT_HAS_ACTIVE_BOOKING", 409)
        val (deletion, calls) = deletionAnswering { answer }

        deletion.confirm()
        runCurrent()
        assertEquals("ACCOUNT_HAS_ACTIVE_BOOKING", deletion.state.value.errorCode)

        // She cancelled the seat and came back.
        answer = ApiResult.Success(Unit)
        deletion.confirm()
        runCurrent()

        assertEquals(2, calls())
        assertTrue(deletion.state.value.deleted)
        assertNull("the old reason must not outlive the retry", deletion.state.value.errorCode)
    }

    @Test
    fun `a second tap while the first is out sends nothing`() = runTest {
        val gate = CompletableDeferred<ApiResult<Unit>>()
        val (deletion, calls) = deletionAnswering { gate.await() }

        deletion.confirm()
        runCurrent()
        assertTrue("the first tap is in flight", deletion.state.value.isDeleting)

        deletion.confirm()
        runCurrent()
        assertEquals("the second tap must not reach the server", 1, calls())

        gate.complete(ApiResult.Success(Unit))
        runCurrent()
        assertEquals(1, calls())
        assertTrue(deletion.state.value.deleted)
    }

    @Test
    fun `two taps in the same frame send one request`() = runTest {
        // Before the first request has even started: the claim is made in the
        // tap itself, not when the coroutine gets round to running.
        val (deletion, calls) = deletionAnswering { ApiResult.Success(Unit) }

        deletion.confirm()
        deletion.confirm()
        runCurrent()

        assertEquals(1, calls())
    }

    @Test
    fun `no connection is a refusal to try again, not a deletion`() = runTest {
        val (deletion, _) = deletionAnswering { ApiResult.Failure(ApiException.offline()) }

        deletion.confirm()
        runCurrent()

        assertEquals(ApiException.OFFLINE, deletion.state.value.errorCode)
        assertFalse(deletion.state.value.deleted)
        assertTrue(deletion.state.value.canDelete)
    }
}
