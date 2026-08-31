package af.velro.data.sync

import af.velro.data.api.ApiResult
import af.velro.data.db.PendingOperationEntity
import af.velro.data.db.VelroDatabase
import af.velro.data.repository.BookingRepository
import af.velro.data.repository.GeographyRepository
import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.util.concurrent.TimeUnit
import kotlinx.serialization.json.Json

/**
 * Replays what was done offline, and refreshes what changed.
 *
 * Runs only on a connection, with exponential backoff. Every queued mutation
 * carries the idempotency key it was created with, so replaying one the server
 * already applied returns the original response rather than booking a second
 * seat.
 *
 * A queued operation is dropped only when the server has definitively rejected
 * it -- never on a transport failure, and never silently.
 */
@HiltWorker
class SyncWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val db: VelroDatabase,
    private val bookings: BookingRepository,
    private val geography: GeographyRepository,
    private val json: Json,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        var retryNeeded = false

        for (operation in db.pendingOperations().pending()) {
            when (val outcome = replay(operation)) {
                Outcome.DONE -> db.pendingOperations().delete(operation.id)
                Outcome.RETRY -> retryNeeded = true
                Outcome.REJECTED -> {
                    // The server refused on the merits. The row stays, with the
                    // error on it, so what happened is inspectable -- this
                    // used to record the failure and then delete the row in
                    // the next line, which kept neither the retry nor the
                    // evidence. Replay reads only unfailed rows, so a dead
                    // operation cannot churn the worker every fifteen minutes.
                    db.pendingOperations().recordFailure(operation.id, outcome.name)
                }
            }
        }

        // Refresh only after the queue has drained, so a cached booking is not
        // overwritten by a server view that predates a pending change.
        if (!retryNeeded) {
            geography.refresh()
            bookings.refreshBookings()
        }

        return if (retryNeeded) Result.retry() else Result.success()
    }

    private suspend fun replay(operation: PendingOperationEntity): Outcome {
        val result = runCatching { dispatch(operation) }.getOrElse { return Outcome.RETRY }
        return when (result) {
            is ApiResult.Success -> Outcome.DONE
            is ApiResult.Failure -> when {
                result.error.code == af.velro.data.api.ApiException.OFFLINE -> Outcome.RETRY
                result.error.isTransient -> Outcome.RETRY
                else -> Outcome.REJECTED
            }
        }
    }

    private suspend fun dispatch(operation: PendingOperationEntity): ApiResult<*> {
        val payload = json.parseToJsonElement(operation.payload)
        return QueuedOperation.execute(
            kind = operation.kind,
            payload = payload,
            idempotencyKey = operation.idempotencyKey,
            bookings = bookings,
        )
    }

    private enum class Outcome { DONE, RETRY, REJECTED }

    companion object {
        private const val UNIQUE_NAME = "velro-sync"

        /**
         * Periodic rather than one-shot: a handset that regains signal in a
         * valley for ninety seconds should use it without the app being open.
         */
        fun schedule(context: Context) {
            val request = PeriodicWorkRequestBuilder<SyncWorker>(15, TimeUnit.MINUTES)
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()

            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                UNIQUE_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request,
            )
        }
    }
}
