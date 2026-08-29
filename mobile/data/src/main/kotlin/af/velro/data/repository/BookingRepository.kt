package af.velro.data.repository

import af.velro.data.api.ApiResult
import af.velro.data.api.BookSeatsRequest
import af.velro.data.api.CancelBookingRequest
import af.velro.data.api.RateTripRequest
import af.velro.data.api.ResponseMapper
import af.velro.data.api.SearchTripsRequest
import af.velro.data.api.VelroApi
import af.velro.data.db.VelroDatabase
import af.velro.domain.Booking
import af.velro.domain.BookingStatus
import af.velro.domain.Lifecycles
import af.velro.domain.RideKind
import af.velro.domain.TripOption
import java.time.Instant
import javax.inject.Inject
import javax.inject.Singleton
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

@Singleton
class BookingRepository @Inject constructor(
    private val api: VelroApi,
    private val db: VelroDatabase,
    private val mapper: ResponseMapper,
) {

    /**
     * Bookings from the cache.
     *
     * This is what makes the app answer "where is my seat" with no signal --
     * the single most important offline case in the product.
     */
    fun recent(limit: Int = 20): Flow<List<Booking>> =
        db.bookings().recent(limit).map { rows -> rows.map { it.toDomain() } }

    fun booking(id: String): Flow<Booking?> =
        db.bookings().booking(id).map { it?.toDomain() }

    fun active(): Flow<List<Booking>> =
        db.bookings()
            .active(Lifecycles.booking.terminalStates.let { terminal ->
                BookingStatus.entries.filter { it !in terminal }.map { it.name }
            })
            .map { rows -> rows.map { it.toDomain() } }

    suspend fun searchTrips(
        originStationId: String,
        destinationId: String,
        seatCount: Int,
        departureAfter: Instant? = null,
        rideKind: RideKind? = null,
    ): ApiResult<List<TripOption>> =
        mapper.call {
            api.searchTrips(
                SearchTripsRequest(
                    origin_station_id = originStationId,
                    destination_id = destinationId,
                    departure_after = departureAfter?.toString(),
                    seat_count = seatCount,
                    ride_kind = rideKind?.name,
                )
            )
        }.map { list -> list.map { it.toDomain() } }

    /**
     * Book seats.
     *
     * The idempotency key is passed in by the screen and survives rotation, so
     * a retry after a dropped connection returns the original booking instead
     * of taking a second seat.
     */
    suspend fun book(
        tripId: String,
        seatCount: Int,
        pickupStationId: String,
        dropoffDestinationId: String,
        idempotencyKey: String,
        note: String? = null,
    ): ApiResult<Booking> {
        val result = mapper.call {
            api.book(
                idempotencyKey,
                BookSeatsRequest(
                    trip_id = tripId,
                    seat_count = seatCount,
                    pickup_station_id = pickupStationId,
                    dropoff_destination_id = dropoffDestinationId,
                    passenger_note = note,
                ),
            )
        }
        if (result is ApiResult.Success) {
            db.bookings().upsert(result.value.toEntity())
        }
        return result.map { it.toDomain() }
    }

    data class BookingPage(
        val bookings: List<Booking>,
        val hasMore: Boolean,
        val nextOffset: Int,
    )

    suspend fun refreshBookings(): ApiResult<List<Booking>> =
        history(limit = 50).map { it.bookings }

    /**
     * A page of history, cached as it arrives.
     *
     * Every page is written to the local database, so scrolling back through
     * history once makes it readable afterwards with no signal -- which is
     * usually when a passenger wants to check what they paid.
     */
    /**
     * What was last seen for this scope, straight from the local database.
     *
     * The statuses are the ones the server used, kept here so the offline view
     * cannot classify a booking differently from the online one.
     */
    suspend fun cachedHistory(statuses: List<BookingStatus>, limit: Int = 50): List<Booking> =
        db.bookings()
            .cachedByStatus(statuses.map { it.name }, limit)
            .map { it.toDomain() }

    suspend fun history(
        limit: Int = 20,
        offset: Int = 0,
        scope: String = "all",
    ): ApiResult<BookingPage> {
        val result = mapper.call { api.bookings(limit = limit, offset = offset, scope = scope) }
        if (result is ApiResult.Success) {
            db.bookings().upsertAll(result.value.bookings.map { it.toEntity() })
        }
        return result.map { page ->
            BookingPage(
                bookings = page.bookings.map { it.toDomain() },
                hasMore = page.has_more,
                nextOffset = page.next_offset,
            )
        }
    }

    suspend fun refreshBooking(id: String): ApiResult<Booking> {
        val result = mapper.call { api.booking(id) }
        if (result is ApiResult.Success) {
            db.bookings().upsert(result.value.toEntity())
        }
        return result.map { it.toDomain() }
    }

    suspend fun cancel(bookingId: String, reasonCode: String): ApiResult<Int> {
        val result = mapper.call {
            api.cancelBooking(bookingId, CancelBookingRequest(reason_code = reasonCode))
        }
        if (result is ApiResult.Success) {
            // Re-read rather than patching the cached row: the server decides
            // the final status and any cancellation fee.
            refreshBooking(bookingId)
        }
        return result.map { it.seats_released }
    }

    suspend fun rate(
        tripId: String,
        score: Int,
        comment: String? = null,
        bookingId: String? = null,
    ): ApiResult<Unit> =
        mapper.call {
            api.rateTrip(tripId, RateTripRequest(score, comment, bookingId))
        }.map { }
}
