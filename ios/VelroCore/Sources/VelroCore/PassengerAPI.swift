import Foundation

/// What a passenger sends to ask for a ride. Times are ISO-8601; nil means
/// "now" and "one way", as the server reads an absent value.
public struct RideAsk: Encodable, Sendable, Equatable {
    public let originStationId: String
    public let destinationId: String
    public let passengerCount: Int
    public let offeredFareMinor: Int64
    public let returnFareMinor: Int64?
    public let note: String?
    public let requestedFor: String?
    public let returnFor: String?
    /// Where the passenger is standing, for the geofence; decimal as text.
    public let latitude: String?
    public let longitude: String?
    public let locationIsMock: Bool

    public init(
        originStationId: String, destinationId: String, passengerCount: Int,
        offeredFareMinor: Int64, returnFareMinor: Int64?, note: String?,
        requestedFor: Date?, returnFor: Date?,
        latitude: Double?, longitude: Double?
    ) {
        self.originStationId = originStationId
        self.destinationId = destinationId
        self.passengerCount = passengerCount
        self.offeredFareMinor = offeredFareMinor
        self.returnFareMinor = returnFareMinor
        let trimmed = note?.trimmingCharacters(in: .whitespacesAndNewlines)
        self.note = trimmed?.isEmpty == false ? trimmed : nil
        self.requestedFor = requestedFor.map(ISODate.format)
        self.returnFor = returnFor.map(ISODate.format)
        self.latitude = latitude.map { String(format: "%.6f", $0) }
        self.longitude = longitude.map { String(format: "%.6f", $0) }
        // iOS does not tell an app whether a fix was simulated the way
        // Android does; nothing is claimed that cannot be known.
        self.locationIsMock = false
    }
}

extension API {
    // MARK: Geography

    /// The whole hierarchy. With the cached `version` the server answers 304
    /// when nothing moved -- usually, because Ghorband's districts do not.
    public static func geoSnapshot(version: String?) -> Endpoint<GeoSnapshot> {
        .get("geo/snapshot", query: version.map { [URLQueryItem(name: "version", value: $0)] } ?? [])
    }

    public static func destinations(from stationId: String) -> Endpoint<[DestinationGroup]> {
        .get("geo/stations/\(stationId)/destinations")
    }

    // MARK: Negotiated fares

    /// The ask rings every online driver; the key makes a retry the same ask.
    public static func requestRide(_ ask: RideAsk, idempotencyKey: String) -> Endpoint<RideRequest> {
        .post("ride-requests", body: ask, idempotencyKey: idempotencyKey)
    }

    public static func myRideRequests() -> Endpoint<[RideRequest]> { .get("ride-requests") }

    public static func cancelRideRequest(_ id: String) -> Endpoint<[String: JSONValue]> {
        .post("ride-requests/\(id)/cancel")
    }

    /// The tap that makes the journey. The answer carries the boarding code,
    /// and the server keeps a replay of it under this passenger alone.
    public static func acceptOffer(_ offerId: String, attemptId: String) -> Endpoint<AcceptedOffer> {
        .post(
            "fare-offers/\(offerId)/accept",
            idempotencyKey: IdempotencyKeys.acceptOffer(offerId: offerId, attemptId: attemptId)
        )
    }

    // MARK: Bookings

    /// "all", "upcoming" or "past" -- decided by the server so both apps agree
    /// on which statuses count as finished.
    public static func bookings(scope: String = "all", limit: Int = 20, offset: Int = 0) -> Endpoint<BookingPage> {
        .get("bookings", query: [
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset)),
            URLQueryItem(name: "scope", value: scope),
        ])
    }

    public static func booking(_ id: String) -> Endpoint<Booking> { .get("bookings/\(id)") }

    public static func cancelBooking(_ id: String) -> Endpoint<CancelledBooking> {
        struct Body: Encodable { let reasonCode = "PASSENGER_CANCELLED" }
        return .post("bookings/\(id)/cancel", body: Body())
    }

    public static func rateTrip(tripId: String, bookingId: String, score: Int, comment: String?) -> Endpoint<[String: JSONValue]> {
        struct Body: Encodable { let score: Int; let comment: String?; let bookingId: String }
        return .post("trips/\(tripId)/rating", body: Body(score: score, comment: comment, bookingId: bookingId))
    }

    /// Null until a driver is on the journey.
    public static func bookingDriver(_ bookingId: String) -> Endpoint<RideDriver> {
        .get("bookings/\(bookingId)/driver")
    }

    /// Null when the car has not reported where it is.
    public static func vehicleLocation(_ bookingId: String) -> Endpoint<VehicleLocation> {
        .get("bookings/\(bookingId)/vehicle-location")
    }

    /// Raw image bytes, and a 404 both when there is no photo and when this
    /// passenger has no live connection to the driver. Read with `data(_:)`.
    public static func driverPhoto(_ driverId: String) -> Endpoint<[String: JSONValue]> {
        .get("drivers/\(driverId)/photo")
    }

    // MARK: Safety

    /// The numbers to dial. Refreshed into a cache whenever there is a
    /// connection, never fetched at the moment somebody needs one.
    public static func safetyContacts() -> Endpoint<SafetyContacts> { .get("support/contacts") }

    public static func raiseTicket(category: String, body: String, tripId: String?, bookingId: String?) -> Endpoint<RaisedTicket> {
        struct Body: Encodable { let categoryCode: String; let subject = ""; let body: String; let tripId: String?; let bookingId: String? }
        return .post("support/tickets", body: Body(categoryCode: category, body: body, tripId: tripId, bookingId: bookingId))
    }

    public static func myTickets() -> Endpoint<[Ticket]> {
        .get("support/tickets", query: [URLQueryItem(name: "limit", value: "30")])
    }

    public static func ticket(_ id: String) -> Endpoint<Ticket> { .get("support/tickets/\(id)") }

    public static func reply(toTicket id: String, body: String) -> Endpoint<[String: JSONValue]> {
        struct Body: Encodable { let body: String }
        return .post("support/tickets/\(id)/messages", body: Body(body: body))
    }
}

extension APIClient {
    /// The body as it came, for the endpoints that answer with an image rather
    /// than an envelope. Same session and token handling as everything else.
    public func data<T>(_ endpoint: Endpoint<T>) async -> Result<Data, APIError> {
        await raw(endpoint)
    }
}
