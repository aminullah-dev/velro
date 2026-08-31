package af.velro.data.sync

import af.velro.data.db.OperationKind
import af.velro.data.db.PendingOperationEntity
import af.velro.data.db.VelroDatabase
import android.content.Context
import androidx.work.Constraints
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import dagger.hilt.android.qualifiers.ApplicationContext
import java.util.UUID
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * The door into the offline queue.
 *
 * The queue's machinery -- table, worker, dispatcher -- existed complete and
 * unreachable: nothing anywhere enqueued an operation, so the "replays what
 * was done offline" promise ran over a permanently empty table. This is the
 * missing enqueue side, and the rules it enforces are the product's, not the
 * transport's:
 *
 * A queued BOOKING is not a seat. The screen that queues one says so in as
 * many words, because a passenger who walks to the station believing a saved
 * request is a booked chair has been harmed by the app, not helped. A queued
 * CANCEL or RATING carries no such risk -- the server refuses duplicates of
 * both -- which is why they queue silently and a booking queues loudly.
 *
 * Every entry keeps the idempotency key it was born with, so a replay of an
 * operation the server already applied returns the original answer instead of
 * doing the work twice.
 */
@Singleton
class SyncQueue @Inject constructor(
    private val db: VelroDatabase,
    @ApplicationContext private val context: Context,
) {

    suspend fun enqueueBooking(
        tripId: String,
        seatCount: Int,
        pickupStationId: String,
        dropoffDestinationId: String,
        idempotencyKey: String,
        note: String? = null,
        latitude: String? = null,
        longitude: String? = null,
        locationIsMock: Boolean = false,
    ) = enqueue(OperationKind.BOOK_SEATS, idempotencyKey,
        PendingPayloads.booking(
            tripId, seatCount, pickupStationId, dropoffDestinationId, note,
            latitude, longitude, locationIsMock,
        ))

    suspend fun enqueueCancel(bookingId: String, reasonCode: String) =
        enqueue(OperationKind.CANCEL_BOOKING, "cancel:$bookingId",
            PendingPayloads.cancel(bookingId, reasonCode))

    suspend fun enqueueRating(
        tripId: String, score: Int, comment: String?, bookingId: String?,
    ) = enqueue(OperationKind.RATE_TRIP, "rate:$tripId:${bookingId ?: "self"}",
        PendingPayloads.rating(tripId, score, comment, bookingId))

    /** Rows the server has definitively refused, for the home screen to show. */
    fun failures(): Flow<List<PendingOperationEntity>> = db.pendingOperations().failures()

    /** How many saved actions are still waiting for a connection. */
    fun pendingCount(): Flow<Int> = db.pendingOperations().pendingCount()

    /** The person has read the failure; the row has done its job. */
    suspend fun dismiss(id: String) = db.pendingOperations().delete(id)

    private suspend fun enqueue(kind: String, key: String, payload: String) {
        db.pendingOperations().upsert(
            PendingOperationEntity(
                id = UUID.randomUUID().toString(),
                kind = kind,
                payload = payload,
                idempotencyKey = key,
                createdAt = System.currentTimeMillis(),
            )
        )
        kick()
    }

    /**
     * A one-shot run the moment a connection exists, beside the 15-minute
     * periodic sweep. Somebody who queues a cancel in a dead zone and walks
     * back into signal should not wait a quarter of an hour for it to land.
     */
    private fun kick() {
        WorkManager.getInstance(context).enqueueUniqueWork(
            "velro-sync-now",
            ExistingWorkPolicy.KEEP,
            OneTimeWorkRequestBuilder<SyncWorker>()
                .setConstraints(
                    Constraints.Builder()
                        .setRequiredNetworkType(NetworkType.CONNECTED)
                        .build()
                )
                .build(),
        )
    }
}

/**
 * Payload builders, pure so a test can hold them against the reader.
 *
 * The keys here and the keys QueuedOperation reads are the same wire format
 * the server takes; a drifted name fails at replay time on a handset in a
 * valley, which is the worst possible place to learn about it.
 */
object PendingPayloads {
    fun booking(
        tripId: String, seatCount: Int,
        pickupStationId: String, dropoffDestinationId: String, note: String?,
        latitude: String?, longitude: String?, locationIsMock: Boolean,
    ): String = buildJsonObject {
        put("trip_id", tripId)
        put("seat_count", seatCount)
        put("pickup_station_id", pickupStationId)
        put("dropoff_destination_id", dropoffDestinationId)
        if (note != null) put("note", note)
        // Where they stood when they tried, not where the worker later runs.
        if (latitude != null) put("latitude", latitude)
        if (longitude != null) put("longitude", longitude)
        if (locationIsMock) put("location_is_mock", true)
    }.toString()

    fun cancel(bookingId: String, reasonCode: String): String = buildJsonObject {
        put("booking_id", bookingId)
        put("reason_code", reasonCode)
    }.toString()

    fun rating(tripId: String, score: Int, comment: String?, bookingId: String?): String =
        buildJsonObject {
            put("trip_id", tripId)
            put("score", score)
            if (comment != null) put("comment", comment)
            if (bookingId != null) put("booking_id", bookingId)
        }.toString()
}
