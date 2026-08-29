package af.velro.data.api

import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * The HTTP surface.
 *
 * Every mutation takes an `Idempotency-Key`. Connections in the target market
 * drop mid-request often enough that a retry is normal, and a request that
 * timed out at the handset very often succeeded at the server -- so a booking
 * must never be created twice by a retry.
 */
interface VelroApi {

    // -- auth -----------------------------------------------------------

    @POST("auth/otp/request")
    suspend fun requestOtp(
        @Body body: RequestOtpRequest,
    ): Response<Envelope<RequestOtpResponse>>

    @POST("auth/otp/verify")
    suspend fun verifyOtp(@Body body: VerifyOtpRequest): Response<Envelope<SessionDto>>

    @POST("auth/refresh")
    suspend fun refresh(@Body body: RefreshRequest): Response<Envelope<SessionDto>>

    @POST("auth/logout-all")
    suspend fun logoutAllDevices(): Response<Envelope<Map<String, Int>>>

    @GET("auth/me")
    suspend fun profile(): Response<Envelope<ProfileDto>>

    @PATCH("auth/me")
    suspend fun updateProfile(
        @Body body: UpdateProfileRequest,
    ): Response<Envelope<ProfileDto>>

    // -- geography ------------------------------------------------------

    /**
     * The whole hierarchy, cached by version.
     *
     * `version` is the client's copy; the server answers 304 when it matches.
     * Geography changes a few times a year, so this is the single biggest
     * saving available on a 2G connection.
     */
    @GET("geo/snapshot")
    suspend fun geoSnapshot(
        @Query("version") version: String? = null,
    ): Response<Envelope<GeoSnapshotDto>>

    @GET("geo/districts")
    suspend fun districts(): Response<Envelope<List<DistrictDto>>>

    @GET("geo/districts/{id}/villages")
    suspend fun villages(
        @Path("id") districtId: String,
        @Query("limit") limit: Int = 200,
    ): Response<Envelope<List<VillageDto>>>

    @GET("geo/villages/{id}/stations")
    suspend fun stations(@Path("id") villageId: String): Response<Envelope<List<StationDto>>>

    @GET("geo/search")
    suspend fun searchPlaces(
        @Query("q") query: String,
        @Query("limit") limit: Int = 20,
    ): Response<Envelope<List<SearchResultDto>>>

    @GET("geo/stations/nearby")
    suspend fun nearbyStations(
        @Query("latitude") latitude: String,
        @Query("longitude") longitude: String,
        @Query("radius_m") radiusMetres: Int = 15_000,
        @Query("limit") limit: Int = 10,
    ): Response<Envelope<List<StationDto>>>

    @GET("geo/stations/{id}/destinations")
    suspend fun destinationsFrom(
        @Path("id") stationId: String,
    ): Response<Envelope<List<DestinationGroupDto>>>

    // -- passenger ------------------------------------------------------

    @POST("trips/search")
    suspend fun searchTrips(
        @Body body: SearchTripsRequest,
    ): Response<Envelope<List<TripOptionDto>>>

    @POST("bookings")
    suspend fun book(
        @Header("Idempotency-Key") idempotencyKey: String,
        @Body body: BookSeatsRequest,
    ): Response<Envelope<BookingDto>>

    @GET("bookings")
    suspend fun bookings(
        @Query("limit") limit: Int = 20,
        @Query("offset") offset: Int = 0,
    ): Response<Envelope<List<BookingDto>>>

    @GET("bookings/{id}")
    suspend fun booking(@Path("id") bookingId: String): Response<Envelope<BookingDto>>

    @POST("bookings/{id}/cancel")
    suspend fun cancelBooking(
        @Path("id") bookingId: String,
        @Body body: CancelBookingRequest,
    ): Response<Envelope<CancelBookingResponse>>

    @POST("trips/{id}/rating")
    suspend fun rateTrip(
        @Path("id") tripId: String,
        @Body body: RateTripRequest,
    ): Response<Envelope<RateTripResponse>>

    // -- driver ---------------------------------------------------------

    @GET("driver/me")
    suspend fun driverProfile(): Response<Envelope<DriverProfileDto>>

    @POST("driver/status")
    suspend fun setDriverStatus(
        @Body body: DriverStatusRequest,
    ): Response<Envelope<Map<String, String>>>

    @GET("driver/offers")
    suspend fun offers(): Response<Envelope<List<OfferDto>>>

    @POST("driver/trips/{id}/accept")
    suspend fun acceptTrip(
        @Path("id") tripId: String,
        @Header("Idempotency-Key") idempotencyKey: String,
    ): Response<Envelope<Map<String, String>>>

    @POST("driver/trips/{id}/advance")
    suspend fun advanceTrip(
        @Path("id") tripId: String,
        @Body body: AdvanceTripRequest,
    ): Response<Envelope<AdvanceTripResponse>>

    @POST("driver/trips/{id}/verify-passenger")
    suspend fun verifyPassenger(
        @Path("id") tripId: String,
        @Body body: VerifyPassengerRequest,
    ): Response<Envelope<VerifyPassengerResponse>>

    @GET("driver/trips/current")
    suspend fun currentTrip(): Response<Envelope<CurrentTripDto?>>

    @POST("driver/location")
    suspend fun pingLocation(
        @Body body: LocationPingRequest,
    ): Response<Envelope<Map<String, Boolean>>>

    @GET("driver/earnings")
    suspend fun earnings(): Response<Envelope<EarningsDto>>
}
