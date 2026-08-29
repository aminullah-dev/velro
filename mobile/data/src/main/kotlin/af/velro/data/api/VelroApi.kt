package af.velro.data.api

import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.Multipart
import retrofit2.http.Part
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

    /**
     * The passenger's own bookings.
     *
     * ``scope`` is "all", "upcoming" or "past" -- the split the history screen
     * shows as tabs, decided by the server so both surfaces agree on which
     * statuses count as finished.
     */
    @GET("bookings")
    suspend fun bookings(
        @Query("limit") limit: Int = 20,
        @Query("offset") offset: Int = 0,
        @Query("scope") scope: String = "all",
    ): Response<Envelope<BookingPageDto>>

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

    // -- negotiated fares, section 89 ------------------------------------

    /**
     * Ask to be driven, at a price the passenger names.
     *
     * There is no endpoint that suggests a fare, because there is no fare to
     * suggest: VELRO does not know the distance between two Ghorband villages
     * or which stretch of the road is dirt.
     */
    @POST("ride-requests")
    suspend fun requestRide(
        @Body body: RequestRideRequest,
    ): Response<Envelope<RideRequestDto>>

    @GET("ride-requests")
    suspend fun myRideRequests(): Response<Envelope<List<RideRequestDto>>>

    @POST("ride-requests/{id}/cancel")
    suspend fun cancelRideRequest(
        @Path("id") id: String,
    ): Response<Envelope<Map<String, String>>>

    @POST("fare-offers/{id}/accept")
    suspend fun acceptOffer(
        @Path("id") id: String,
    ): Response<Envelope<AcceptedOfferDto>>

    @GET("driver/ride-requests")
    suspend fun openRideRequests(
        @Query("station_id") stationId: String? = null,
        @Query("limit") limit: Int = 30,
    ): Response<Envelope<List<RideRequestDto>>>

    @POST("driver/ride-requests/{id}/offer")
    suspend fun offerFare(
        @Path("id") id: String,
        @Body body: OfferFareRequest,
    ): Response<Envelope<FareOfferDto>>

    @POST("driver/fare-offers/{id}/withdraw")
    suspend fun withdrawOffer(
        @Path("id") id: String,
    ): Response<Envelope<Map<String, String>>>

    @GET("driver/fare-offers")
    suspend fun myFareOffers(): Response<Envelope<List<FareOfferDto>>>

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

    @GET("driver/earnings/ledger")
    suspend fun ledger(
        @Query("limit") limit: Int = 30,
        @Query("offset") offset: Int = 0,
    ): Response<Envelope<LedgerPageDto>>

    @GET("driver/settlements")
    suspend fun payoutOptions(): Response<Envelope<PayoutOptionsDto>>

    /**
     * Ask to be paid.
     *
     * An absent amount means "all of it". The server holds the money against
     * the request, so a repeat while one is open is refused rather than
     * quietly holding it twice.
     */
    @POST("driver/settlements")
    suspend fun requestSettlement(
        @Body body: RequestSettlementRequest,
    ): Response<Envelope<SettlementDto>>

    // -- vehicle --------------------------------------------------------

    @GET("vehicle-types")
    suspend fun vehicleTypes(): Response<Envelope<List<VehicleTypeDto>>>

    @GET("driver/vehicle")
    suspend fun currentVehicle(): Response<Envelope<VehicleDto?>>

    /**
     * Register or replace the vehicle.
     *
     * One endpoint for both because the driver is answering one question --
     * "which car am I driving?" -- and the server decides from the plate
     * whether that is an edit or a different car.
     */
    @POST("driver/vehicle")
    suspend fun registerVehicle(
        @Body body: RegisterVehicleRequest,
    ): Response<Envelope<RegisteredVehicleDto>>

    // -- documents ------------------------------------------------------

    @POST("driver/register")
    suspend fun registerAsDriver(
        @Body body: RegisterDriverRequest,
    ): Response<Envelope<Map<String, String>>>

    @GET("driver/documents")
    suspend fun documents(): Response<Envelope<DocumentChecklistDto>>

    /**
     * Upload one document.
     *
     * Multipart, and deliberately not idempotent-keyed: every upload is a new
     * attempt that supersedes the last, so a retry creating a second row is
     * the correct outcome rather than a duplicate to guard against.
     */
    @Multipart
    @POST("driver/documents")
    suspend fun uploadDocument(
        @Part file: MultipartBody.Part,
        @Part("document_type_code") documentTypeCode: RequestBody,
    ): Response<Envelope<UploadedDocumentDto>>

    // -- the car's own papers -------------------------------------------
    //
    // Keyed by vehicle, not by driver. A driver with two cars owes two جواز
    // سیر, and the first cannot certify the second.

    @GET("driver/vehicles/{vehicleId}/documents")
    suspend fun vehicleDocuments(
        @Path("vehicleId") vehicleId: String,
    ): Response<Envelope<VehicleChecklistDto>>

    @Multipart
    @POST("driver/vehicles/{vehicleId}/documents")
    suspend fun uploadVehicleDocument(
        @Path("vehicleId") vehicleId: String,
        @Part file: MultipartBody.Part,
        @Part("document_type_code") documentTypeCode: RequestBody,
    ): Response<Envelope<UploadedDocumentDto>>

    // -- the inbox ------------------------------------------------------
    //
    // The row in the inbox is the record; a push, when there is one, is a
    // convenience on top of it. Without this client the server writes
    // "your fare was accepted" and nothing on the phone ever reads it.

    @GET("notifications")
    suspend fun notifications(
        @Query("limit") limit: Int = 30,
    ): Response<Envelope<InboxDto>>

    @POST("notifications/read")
    suspend fun markNotificationsRead(
        @Body body: MarkReadRequest,
    ): Response<Envelope<Map<String, Int>>>

    // -- safety ---------------------------------------------------------

    /**
     * The numbers to dial. The one endpoint that needs no token.
     *
     * Called to refresh a cached copy when there happens to be a connection,
     * never at the moment somebody needs a number -- by then it is too late
     * to ask.
     */
    @GET("support/contacts")
    suspend fun safetyContacts(): Response<Envelope<SafetyContactsDto>>

    @POST("support/tickets")
    suspend fun raiseTicket(
        @Body body: RaiseTicketRequest,
    ): Response<Envelope<RaisedTicketDto>>
}
