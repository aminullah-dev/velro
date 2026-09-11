import Foundation
import Testing
@testable import VelroCore

private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
    try APIClient.decoder().decode(T.self, from: Data(json.utf8))
}

private let profileJSON = #"""
{"id":"d1","user_id":"u1","full_name":"محمد","approval_status":"APPROVED","availability":"ONLINE",
 "rating_average":5.0,"rating_count":2,"completed_trips":10,"missing_documents":[],
 "vehicle":{"id":"v1","vehicle_type_code":"SEDAN","plate_number":"PRW-1234","seat_capacity":4,
            "brand":"Toyota","model":"Corolla","year":2012,"colour":null,"status":"ACTIVE"}}
"""#

private let currentJSON = #"""
{"trip":{"id":"t1","number":"TR-1","status":"BOARDING","ride_kind":"NEGOTIATED",
         "scheduled_departure_at":"2026-09-12T02:30:00+00:00","origin_station_id":"s1",
         "origin_station_name":"ایستگاه بابر","destination_id":"x1","destination_name":"چاریکار",
         "seat_capacity":4,"seats_available":1,"driver_id":"d1","vehicle_id":"v1"},
 "manifest":[
   {"booking_id":"b1","number":"BK-1","status":"ONBOARD","seat_count":1,"pickup_station_id":"s1",
    "dropoff_destination_id":"x1","passenger_name":null,"passenger_phone":"+93700000800",
    "fare_total_minor":30000,"fare_currency":"AFN"},
   {"booking_id":"b2","number":"BK-2","status":"READY","seat_count":2,"pickup_station_id":"s1",
    "dropoff_destination_id":"x1","passenger_phone":"+93700000801"},
   {"booking_id":"b3","number":"BK-3","status":"NO_SHOW","seat_count":1,"pickup_station_id":"s1",
    "dropoff_destination_id":"x1"}]}
"""#

@Suite("The driver's rules")
struct DriverRulesTests {
    @Test func anApprovedDriverWithAnActiveCarMayWork() throws {
        let profile = try decode(DriverProfile.self, profileJSON)
        #expect(profile.canWork)
        #expect(profile.isOnline)
        #expect(!profile.blockedByVehicle)
        #expect(profile.vehicle?.makeAndModel == "Toyota Corolla")
    }

    @Test func aCarAwaitingReviewShutsTheGateOnTheVehicleSide() throws {
        let json = profileJSON.replacingOccurrences(of: #""status":"ACTIVE""#, with: #""status":"PENDING""#)
        let profile = try decode(DriverProfile.self, json)
        #expect(!profile.canWork)
        #expect(profile.blockedByVehicle)
    }

    @Test func aMissingPaperShutsTheGateOnThePersonSide() throws {
        let json = profileJSON.replacingOccurrences(of: #""missing_documents":[]"#, with: #""missing_documents":["SELFIE"]"#)
        let profile = try decode(DriverProfile.self, json)
        #expect(!profile.canWork)
        #expect(!profile.blockedByVehicle)
    }

    @Test func anUnknownAvailabilityReadsAsOfflineRatherThanFailingTheScreen() throws {
        let json = profileJSON.replacingOccurrences(of: #""availability":"ONLINE""#, with: #""availability":"ON_A_BREAK""#)
        #expect(try decode(DriverProfile.self, json).availability == .offline)
    }

    @Test func eachStepOffersOnlyTheOneTheServerWouldAccept() {
        #expect(TripStatus.driverAssigned.nextStep == .driverArriving)
        #expect(TripStatus.driverArriving.nextStep == .arrivedAtPickup)
        #expect(TripStatus.arrivedAtPickup.nextStep == .boarding)
        #expect(TripStatus.boarding.nextStep == .inTransit)
        #expect(TripStatus.inTransit.nextStep == .arrived)
        #expect(TripStatus.arrived.nextStep == .completed)
        #expect(TripStatus.completed.nextStep == nil)
        #expect(TripStatus.cancelled.nextStep == nil)
    }

    @Test func aMovingCarCannotBeCalledOff() {
        #expect(TripStatus.boarding.isCancellable)
        #expect(!TripStatus.inTransit.isCancellable)
        #expect(!TripStatus.arrived.isCancellable)
    }

    @Test func codesAreCheckedOnlyAtTheCar() {
        #expect(TripStatus.arrivedAtPickup.acceptsBoardingCodes)
        #expect(TripStatus.boarding.acceptsBoardingCodes)
        #expect(!TripStatus.driverArriving.acceptsBoardingCodes)
        #expect(!TripStatus.inTransit.acceptsBoardingCodes)
    }

    @Test func theManifestCountsWhoIsStillExpectedAndWhoIsUnchecked() throws {
        let current = try decode(CurrentAssignment.self, currentJSON)
        #expect(current.passengers.map(\.bookingId) == ["b1", "b2"])
        #expect(current.unverified == 1)
        // Boarding, one unchecked: the next tap pulls away with somebody
        // unchecked, so it is asked about first.
        #expect(current.startsWithUnverified)
        #expect(current.passengers.first?.fare == Money(amountMinor: 30000))
        #expect(current.trip.originStationName == "ایستگاه بابر")
    }

    @Test func noCurrentTripIsAnAnswerNotAFailure() throws {
        struct Wrapped: Decodable { let data: CurrentAssignment? }
        #expect(try decode(Wrapped.self, #"{"data":null}"#).data == nil)
    }

    @Test func aCashDriverOwesTheNegativeOfHisBalance() throws {
        let earnings = try decode(Earnings.self, #"""
        {"available":{"amount_minor":-55800,"currency":"AFN"},"pending":{"amount_minor":0,"currency":"AFN"},
         "lifetime_earned":{"amount_minor":682200,"currency":"AFN"},"lifetime_commission":{"amount_minor":55800,"currency":"AFN"},
         "lifetime_paid":{"amount_minor":0,"currency":"AFN"},"completed_trips":10}
        """#)
        #expect(earnings.owes)
        #expect(earnings.headline == Money(amountMinor: 55800))
    }

    @Test func aSettlementInFlightDoesNotMakeTheDebtDisappear() throws {
        // 308 still in his pocket and 250 already on its way to the office:
        // he owes 558 until the office marks it paid.
        let earnings = try decode(Earnings.self, #"""
        {"available":{"amount_minor":-30800,"currency":"AFN"},"pending":{"amount_minor":-25000,"currency":"AFN"},
         "lifetime_earned":{"amount_minor":682200,"currency":"AFN"},"lifetime_commission":{"amount_minor":75800,"currency":"AFN"},
         "lifetime_paid":{"amount_minor":100000,"currency":"AFN"},"completed_trips":10}
        """#)
        #expect(earnings.owes)
        #expect(earnings.headline == Money(amountMinor: 55800))
    }

    @Test func aPayoutInFlightIsStillHis() throws {
        // A full payout asked for, then one more cash trip: available is the
        // commission on that trip, below zero, but the wallet as a whole is his.
        let earnings = try decode(Earnings.self, #"""
        {"available":{"amount_minor":-5000,"currency":"AFN"},"pending":{"amount_minor":40000,"currency":"AFN"},
         "lifetime_earned":{"amount_minor":90000,"currency":"AFN"},"lifetime_commission":{"amount_minor":9000,"currency":"AFN"},
         "completed_trips":3}
        """#)
        #expect(!earnings.owes)
        #expect(earnings.headline == Money(amountMinor: 35000))
    }

    @Test func aNotificationPayloadWithANumberStillDecodes() throws {
        // The Android client once refused the whole inbox over a number in a
        // payload it expected to be text.
        let inbox = try decode(Inbox.self, #"""
        {"notifications":[{"id":"n1","message_key":"notif.offer.accepted","payload":{"amount_minor":30000,"route":"بابر"},
          "channel":"IN_APP","delivery_status":"SENT","trip_id":"t1","created_at":"2026-09-11T03:00:00+00:00","read_at":null}],
         "unread":1}
        """#)
        let note = try #require(inbox.notifications?.first)
        #expect(note.isUnread)
        #expect(note.arguments["amount_minor"] as? Int64 == 30000)
    }

    @Test func theDriversBoardReadsWhoIsAskingAndWhetherHeHasOffered() throws {
        let request = try decode(RideRequest.self, #"""
        {"id":"r1","status":"OPEN","origin_station_id":"s1","origin_station_name":"ایستگاه بابر","destination_id":"x1",
         "destination_name":"چاریکار","passenger_count":2,"offered_fare":{"amount_minor":30000,"currency":"AFN"},
         "requested_for":"2026-09-12T02:30:00+00:00","expires_at":"2026-09-11T04:00:00+00:00",
         "passenger_name":"مریم","already_offered":true,"offers":[]}
        """#)
        #expect(request.alreadyOffered == true)
        #expect(request.passengerName == "مریم")
    }

    @Test func aServerDayIsTheSameDayInEveryTimeZone() throws {
        let day = try #require(ISODate.parseDay("2026-09-10"))
        var kabul = Calendar(identifier: .gregorian)
        kabul.timeZone = TimeZone(identifier: "Asia/Kabul")!
        #expect(kabul.component(.day, from: day) == 10)
        #expect(ISODate.parseDay("10/09/2026") == nil)
    }
}

@Suite("A driver's papers")
struct DriverPapersTests {
    private let today = ISODate.parseDay("2026-09-11")!

    @Test func aPaperAMonthOutIsWarnedAbout() {
        #expect(DocumentExpiry.notice(expiresOn: "2026-10-11", today: today)?.severity == .soon)
        #expect(DocumentExpiry.notice(expiresOn: "2026-10-12", today: today)?.severity == .fine)
    }

    @Test func aPaperPastItsDateSaysSo() {
        #expect(DocumentExpiry.notice(expiresOn: "2026-09-10", today: today)?.messageKey == "driver.documents.expired")
        #expect(DocumentExpiry.notice(expiresOn: "2026-09-11", today: today)?.severity == .soon)
        #expect(DocumentExpiry.notice(expiresOn: nil, today: today) == nil)
    }

    @Test func theHeadlineSaysWhatIsLeftToDo() throws {
        func checklist(missing: [String], canWork: Bool) throws -> DocumentChecklist {
            let json = #"{"required":["LICENSE","NATIONAL_ID","SELFIE"],"missing":\#(missing.description),"documents":[],"approval_status":"PENDING","can_work":\#(canWork)}"#
            return try decode(DocumentChecklist.self, json)
        }
        #expect(try checklist(missing: ["SELFIE"], canWork: false).headlineKey == "driver.documents.incomplete")
        #expect(try checklist(missing: [], canWork: false).headlineKey == "driver.documents.awaiting_review")
        #expect(try checklist(missing: [], canWork: true).headlineKey == "driver.documents.approved")
    }
}

@Suite("Driver endpoints")
struct DriverEndpointTests {
    @Test func aDocumentUploadIsOneFileAndItsTypeAsMultipart() throws {
        let photo = Data([0xFF, 0xD8, 0xFF, 0xE0])
        let endpoint = API.uploadDocument(type: "LICENSE", file: .jpeg(photo, name: "licence.jpg"))
        #expect(endpoint.method == .post)
        #expect(endpoint.path == "driver/documents")
        let type = try #require(endpoint.contentType)
        #expect(type.hasPrefix("multipart/form-data; boundary="))
        let boundary = String(type.dropFirst("multipart/form-data; boundary=".count))
        let body = try #require(endpoint.body)
        let text = String(decoding: body, as: UTF8.self)
        #expect(text.contains("--\(boundary)\r\nContent-Disposition: form-data; name=\"document_type_code\"\r\n\r\nLICENSE\r\n"))
        #expect(text.contains("Content-Disposition: form-data; name=\"file\"; filename=\"licence.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n"))
        #expect(text.hasSuffix("--\(boundary)--\r\n"))
        #expect(body.range(of: photo) != nil)
    }

    @Test func aLocationPingSendsDecimalsAsTextAndDropsAnUnknownHeading() throws {
        let endpoint = API.pingLocation(latitude: 34.9619424, longitude: 68.5970518, heading: -1, accuracy: 12.4, at: Date(timeIntervalSince1970: 0))
        let body = try #require(endpoint.body)
        let json = try #require(try JSONSerialization.jsonObject(with: body) as? [String: Any])
        #expect(json["latitude"] as? String == "34.961942")
        #expect(json["longitude"] as? String == "68.597052")
        #expect(json["heading_degrees"] == nil)
        #expect(json["accuracy_m"] as? Int == 12)
        #expect(json["recorded_at"] as? String == "1970-01-01T00:00:00Z")
    }

    @Test func anOfferWithoutAReturnSendsNoReturnLegAndNoEmptyNote() throws {
        let endpoint = API.offerFare(requestId: "r1", amountMinor: 35000, returnAmountMinor: nil, note: "   ")
        let body = try #require(endpoint.body)
        let json = try #require(try JSONSerialization.jsonObject(with: body) as? [String: Any])
        #expect(json["amount_minor"] as? Int == 35000)
        #expect(json.keys.sorted() == ["amount_minor"])
    }

    @Test func acceptingADispatchedTripIsKeyedLikeAndroid() {
        #expect(API.acceptTrip("t1", driverId: "d1").idempotencyKey == "accept:t1:d1")
    }

    @Test func aPlateIsSentTrimmedAndUpperCase() throws {
        let endpoint = API.registerVehicle(typeCode: "SEDAN", plate: " prw-1234 ", seats: 4, brand: "", model: "Corolla", year: nil, colour: nil)
        let body = try #require(endpoint.body)
        let json = try #require(try JSONSerialization.jsonObject(with: body) as? [String: Any])
        #expect(json["plate_number"] as? String == "PRW-1234")
        #expect(json["brand"] == nil)
        #expect(json["model"] as? String == "Corolla")
    }
}
