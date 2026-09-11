import Foundation

// Every call the driver app makes, in the shapes the Android app's
// `VelroApi` sends: the server cannot tell the two clients apart, and must
// not need to.

extension API {
    // MARK: The driver

    /// 403 PERMISSION_DENIED for somebody signed in who is not a driver yet:
    /// the apply form, not an error page.
    public static func driverProfile() -> Endpoint<DriverProfile> { .get("driver/me") }

    public static func setAvailability(_ availability: DriverAvailability) -> Endpoint<[String: JSONValue]> {
        struct Body: Encodable { let availability: String }
        return .post("driver/status", body: Body(availability: availability.rawValue))
    }

    /// A passenger applying to drive. The name is optional: an operator fills
    /// a blank one from the tazkira at approval.
    public static func registerAsDriver(fullName: String?) -> Endpoint<[String: JSONValue]> {
        struct Body: Encodable { let fullName: String? }
        let trimmed = fullName?.trimmingCharacters(in: .whitespacesAndNewlines)
        return .post("driver/register", body: Body(fullName: trimmed?.isEmpty == false ? trimmed : nil))
    }

    // MARK: The board -- passengers who named a price

    public static func openRideRequests(limit: Int = 30) -> Endpoint<[RideRequest]> {
        .get("driver/ride-requests", query: [URLQueryItem(name: "limit", value: String(limit))])
    }

    /// His price. The return leg is required exactly when the passenger asked
    /// for a return, and absent otherwise.
    public static func offerFare(requestId: String, amountMinor: Int64, returnAmountMinor: Int64?, note: String?) -> Endpoint<FareOffer> {
        struct Body: Encodable { let amountMinor: Int64; let returnAmountMinor: Int64?; let note: String? }
        let trimmed = note?.trimmingCharacters(in: .whitespacesAndNewlines)
        return .post(
            "driver/ride-requests/\(requestId)/offer",
            body: Body(amountMinor: amountMinor, returnAmountMinor: returnAmountMinor, note: trimmed?.isEmpty == false ? trimmed : nil)
        )
    }

    public static func withdrawOffer(_ offerId: String) -> Endpoint<[String: JSONValue]> {
        .post("driver/fare-offers/\(offerId)/withdraw")
    }

    public static func myFareOffers() -> Endpoint<[FareOffer]> { .get("driver/fare-offers") }

    // MARK: Trips

    /// Trips the dispatcher offered him.
    public static func dispatchOffers() -> Endpoint<[DispatchOffer]> { .get("driver/offers") }

    /// Keyed by trip and driver, as Android keys it: a retry after a lost
    /// answer is the same accept, not a second one.
    public static func acceptTrip(_ tripId: String, driverId: String) -> Endpoint<[String: JSONValue]> {
        .post("driver/trips/\(tripId)/accept", idempotencyKey: "accept:\(tripId):\(driverId)")
    }

    /// Null when he has no trip: `sendNullable`.
    public static func currentTrip() -> Endpoint<CurrentAssignment> { .get("driver/trips/current") }

    public static func advanceTrip(_ tripId: String, to target: TripStatus, reasonCode: String? = nil, note: String? = nil) -> Endpoint<AdvanceOutcome> {
        struct Body: Encodable { let target: String; let reasonCode: String?; let note: String? }
        let trimmed = note?.trimmingCharacters(in: .whitespacesAndNewlines)
        return .post(
            "driver/trips/\(tripId)/advance",
            body: Body(target: target.rawValue, reasonCode: reasonCode, note: trimmed?.isEmpty == false ? trimmed : nil)
        )
    }

    public static func verifyPassenger(tripId: String, code: String) -> Endpoint<VerifiedPassenger> {
        struct Body: Encodable { let code: String }
        return .post("driver/trips/\(tripId)/verify-passenger", body: Body(code: code))
    }

    public static func tripMap(_ tripId: String) -> Endpoint<TripMap> { .get("driver/trips/\(tripId)/map") }

    /// Where the car is. Decimal as text, as the server reads it, so no float
    /// rounding moves the car on the passenger's map.
    public static func pingLocation(latitude: Double, longitude: Double, heading: Double?, accuracy: Double?, at: Date) -> Endpoint<[String: JSONValue]> {
        struct Body: Encodable {
            let latitude: String
            let longitude: String
            let headingDegrees: Int?
            let accuracyM: Int?
            let recordedAt: String
        }
        let degrees = heading.flatMap { $0 >= 0 ? Int($0.rounded()) % 360 : nil }
        return .post("driver/location", body: Body(
            latitude: String(format: "%.6f", latitude),
            longitude: String(format: "%.6f", longitude),
            headingDegrees: degrees,
            accuracyM: accuracy.flatMap { $0 >= 0 ? Int($0.rounded()) : nil },
            recordedAt: ISODate.format(at)
        ))
    }

    /// The driver scoring the passenger who has just travelled.
    public static func ratePassenger(tripId: String, bookingId: String, score: Int) -> Endpoint<[String: JSONValue]> {
        rateTrip(tripId: tripId, bookingId: bookingId, score: score, comment: nil)
    }

    // MARK: Money

    public static func earnings() -> Endpoint<Earnings> { .get("driver/earnings") }

    /// "day", "week" or "month".
    public static func earningsSummary(period: String, buckets: Int) -> Endpoint<EarningsSummary> {
        .get("driver/earnings/summary", query: [
            URLQueryItem(name: "period", value: period),
            URLQueryItem(name: "buckets", value: String(buckets)),
        ])
    }

    public static func ledger(limit: Int = 30, offset: Int = 0) -> Endpoint<LedgerPage> {
        .get("driver/earnings/ledger", query: [
            URLQueryItem(name: "limit", value: String(limit)),
            URLQueryItem(name: "offset", value: String(offset)),
        ])
    }

    public static func payoutOptions() -> Endpoint<PayoutOptions> { .get("driver/settlements") }

    // MARK: The car

    public static func vehicleTypes() -> Endpoint<[VehicleType]> { .get("vehicle-types") }

    /// Null before he has registered one: `sendNullable`.
    public static func currentVehicle() -> Endpoint<DriverVehicle> { .get("driver/vehicle") }

    /// Register or replace: the server decides from the plate whether this is
    /// an edit or a different car.
    public static func registerVehicle(
        typeCode: String, plate: String, seats: Int?, brand: String?, model: String?, year: Int?, colour: String?
    ) -> Endpoint<RegisteredVehicle> {
        struct Body: Encodable {
            let vehicleTypeCode: String
            let plateNumber: String
            let seatCapacity: Int?
            let brand: String?
            let model: String?
            let year: Int?
            let colour: String?
        }
        func clean(_ text: String?) -> String? {
            let trimmed = text?.trimmingCharacters(in: .whitespacesAndNewlines)
            return trimmed?.isEmpty == false ? trimmed : nil
        }
        return .post("driver/vehicle", body: Body(
            vehicleTypeCode: typeCode,
            plateNumber: plate.trimmingCharacters(in: .whitespacesAndNewlines).uppercased(),
            seatCapacity: seats, brand: clean(brand), model: clean(model), year: year, colour: clean(colour)
        ))
    }

    // MARK: Papers

    public static func documents() -> Endpoint<DocumentChecklist> { .get("driver/documents") }

    /// Not idempotency-keyed: every upload is a new attempt that supersedes
    /// the last, so a retry making a second row is the correct outcome.
    public static func uploadDocument(type: String, file: Upload) -> Endpoint<UploadedDocument> {
        .multipart("driver/documents", fields: ["document_type_code": type], file: file)
    }

    public static func vehicleDocuments(vehicleId: String) -> Endpoint<VehicleChecklist> {
        .get("driver/vehicles/\(vehicleId)/documents")
    }

    public static func uploadVehicleDocument(vehicleId: String, type: String, file: Upload) -> Endpoint<UploadedDocument> {
        .multipart("driver/vehicles/\(vehicleId)/documents", fields: ["document_type_code": type], file: file)
    }

    // MARK: The inbox

    public static func inbox(limit: Int = 20) -> Endpoint<Inbox> {
        .get("notifications", query: [URLQueryItem(name: "limit", value: String(limit))])
    }

    /// No ids means all of them.
    public static func markInboxRead(ids: [String] = []) -> Endpoint<[String: JSONValue]> {
        struct Body: Encodable { let ids: [String] }
        return .post("notifications/read", body: Body(ids: ids))
    }
}
