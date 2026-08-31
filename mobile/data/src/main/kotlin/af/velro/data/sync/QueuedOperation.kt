package af.velro.data.sync

import af.velro.data.api.ApiResult
import af.velro.data.db.OperationKind
import af.velro.data.repository.BookingRepository
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.int
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * What a queued mutation replays as.
 *
 * Kept apart from the worker so the mapping from a stored payload to an API
 * call is readable in one place, and so a new queued operation is one branch
 * rather than a change to the worker's control flow.
 */
object QueuedOperation {

    suspend fun execute(
        kind: String,
        payload: JsonElement,
        idempotencyKey: String,
        bookings: BookingRepository,
    ): ApiResult<*> {
        val body = payload.jsonObject
        fun string(key: String) = body[key]!!.jsonPrimitive.content
        fun int(key: String) = body[key]!!.jsonPrimitive.int
        fun stringOrNull(key: String) = body[key]?.jsonPrimitive?.content

        return when (kind) {
            OperationKind.BOOK_SEATS -> bookings.book(
                tripId = string("trip_id"),
                seatCount = int("seat_count"),
                pickupStationId = string("pickup_station_id"),
                dropoffDestinationId = string("dropoff_destination_id"),
                idempotencyKey = idempotencyKey,
                note = stringOrNull("note"),
                latitude = stringOrNull("latitude"),
                longitude = stringOrNull("longitude"),
                locationIsMock = body["location_is_mock"]?.jsonPrimitive?.content == "true",
            )

            OperationKind.CANCEL_BOOKING -> bookings.cancel(
                bookingId = string("booking_id"),
                reasonCode = string("reason_code"),
            )

            OperationKind.RATE_TRIP -> bookings.rate(
                tripId = string("trip_id"),
                score = int("score"),
                comment = stringOrNull("comment"),
                bookingId = stringOrNull("booking_id"),
            )

            else -> ApiResult.Failure(
                af.velro.data.api.ApiException(
                    code = "VALIDATION_FAILED",
                    httpStatus = 400,
                    context = mapOf("kind" to kind),
                )
            )
        }
    }
}
