import Foundation
import Testing
@testable import VelroCore

// The operations console's shapes, read from answers the local API actually
// gave (trimmed), and its endpoints' paths, methods and bodies.

private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
    try APIClient.decoder().decode(T.self, from: Data(json.utf8))
}

private func body(_ endpoint: Endpoint<some Decodable & Sendable>) throws -> [String: Any] {
    let data = try #require(endpoint.body)
    return try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
}

private func query(_ endpoint: Endpoint<some Decodable & Sendable>) -> [String: String] {
    Dictionary(uniqueKeysWithValues: endpoint.query.map { ($0.name, $0.value ?? "") })
}

// MARK: - Fixtures

private let dashboardJSON = #"""
{"generated_at":"2026-09-15T03:15:59.146050Z",
 "live":{"on_the_way":0,"at_the_station":1,"moving":2,"departing_soon":3},
 "attention":{"unassigned_trips":0,"departures_at_risk":0,"overdue_trips":11,"open_requests":0,
   "unanswered_requests":0,"pending_drivers":0,"pending_vehicles":2,"pending_documents":0,
   "expiring_documents":0,"open_tickets":13,"stale_gps_drivers":7},
 "today":{"trips":1,"bookings":0,"completed_trips":0,"cancellations":0,"seats_capacity":4,"seats_sold":1,"utilisation_percent":25},
 "capacity":{"upcoming_trips":0,"nearly_full_trips":0,"empty_departures":0},
 "drivers":{"online":7,"on_trip":0,"offline":1,"pending":0,"suspended":0,"total":8,"without_fix":7},
 "finance":{"currency":"AFN","revenue_today_minor":0,"commission_today_minor":0,"driver_earnings_today_minor":0,
   "cash_owed_minor":70560,"payouts_due_minor":0,"settlements_open":1},
 "network":{"routes_active":2983,"stations":427,"villages":427,"villages_without_coordinates":372,
   "villages_without_stations":0,"stations_without_routes":0,"routes_without_upcoming_trips":2983},
 "people":{"passengers":63,"drivers":8},
 "history":{"currency":"AFN","days":[
   {"date":"2026-09-09","trips":0,"bookings":0,"completed_trips":0,"cancellations":0,"revenue_minor":0,"commission_minor":0},
   {"date":"2026-09-10","trips":0,"bookings":7,"completed_trips":0,"cancellations":7,"revenue_minor":62200,"commission_minor":6220}]},
 "apps":{"window_days":7,"latest":{"passenger":null,"driver":{"version_code":6,"version_name":"1.2.3"}},
   "versions":[{"app":"driver","platform":"android","version_code":6,"version_name":"1.2.3","checks":3},
               {"app":"driver","platform":"ios","version_code":2,"version_name":"1.0.0","checks":1}]}}
"""#

private let liveMapJSON = #"""
{"generated_at":"2026-09-15T03:15:59.225377Z","stale_after_seconds":300,"drivers":[
 {"driver_id":"d1","name":"احمد","phone":"+93700000010","availability":"ONLINE",
  "vehicle":{"plate":"PRW-9911","brand":"Toyota","model":"Corolla"},
  "location":{"latitude":34.5553,"longitude":69.2075,"heading_degrees":90,"recorded_at":"2026-09-14T22:09:12.300979-04:00","stale":true},
  "trip":null,"rehearsing":false},
 {"driver_id":"d2","name":null,"phone":"+12025550142","availability":"ON_TRIP","vehicle":null,
  "location":{"latitude":34.96,"longitude":68.59,"heading_degrees":null,"recorded_at":"2026-09-15T03:15:00Z","stale":false},
  "trip":{"id":"t9","number":46,"status":"IN_TRANSIT","origin_name":"ایستگاه بابر","destination_name":"چاریکار"},
  "rehearsing":true},
 {"driver_id":"d3","name":"نجیب","phone":null,"availability":"ONLINE","vehicle":null,"location":null,"trip":null,"rehearsing":false}]}
"""#

private let tripsJSON = #"""
{"success":true,"data":[
 {"id":"t1","number":"VLR-2026-000046","status":"COMPLETED","ride_kind":"PRIVATE",
  "scheduled_departure_at":"2026-09-14T22:30:00-04:00","origin_station_name":"ایستگاه خیشکی",
  "destination_name":"چاریکار","driver_name":"محمد","driver_phone":"+93700000020","plate_number":"PRW-1234",
  "seat_capacity":4,"seats_available":3,"booked_seats":1},
 {"id":"t2","number":"VLR-2026-000047","status":"SCHEDULED","ride_kind":"SHARED",
  "scheduled_departure_at":"2026-09-16T02:30:00+00:00","origin_station_name":"ایستگاه بابر",
  "destination_name":"کابل","driver_name":null,"driver_phone":null,"plate_number":null,
  "seat_capacity":4,"seats_available":4,"booked_seats":0}],
 "message":null,"meta":{"total":46,"limit":2,"offset":0}}
"""#

private let settlementsJSON = #"""
[{"id":"s1","reference":"STL-2026-000003","amount":{"amount_minor":25000,"currency":"AFN"},"direction":"COLLECTION",
  "status":"PENDING","period_start":"2026-08-29","period_end":"2026-08-29","paid_at":null,"rejection_reason":null,
  "driver_id":"d1","driver_name":"محمد","driver_phone":"+93700000020"}]
"""#

private let debtorsJSON = #"""
[{"driver_id":"d1","driver_name":"محمد","driver_phone":"+93700000020","amount_owed":{"amount_minor":66560,"currency":"AFN"},"completed_trips":17},
 {"driver_id":"d2","driver_name":null,"driver_phone":null,"amount_owed":{"amount_minor":4000,"currency":"AFN"},"completed_trips":1}]
"""#

private let driverDocumentsJSON = #"""
{"required":["LICENSE","NATIONAL_ID"],"missing":["LICENSE"],
 "documents":[
  {"id":"doc2","document_type_code":"LICENSE","status":"REJECTED","expires_on":null,"rejection_reason":"blurry",
   "uploaded_at":"2026-09-14T09:56:21.119989-04:00","reviewed_at":"2026-09-14T10:00:00-04:00","is_current":true},
  {"id":"doc1","document_type_code":"NATIONAL_ID","status":"VERIFIED","expires_on":"2027-03-20","rejection_reason":null,
   "uploaded_at":"2026-09-14T09:56:21.119989-04:00","reviewed_at":"2026-09-14T09:56:21.035144-04:00","is_current":true}],
 "approval_status":"PENDING","can_work":false}
"""#

private let vehicleDocumentsJSON = #"""
{"vehicle_id":"v1","plate_number":"PRW 88 12","required":["VEHICLE_REGISTRATION"],"missing":["VEHICLE_REGISTRATION"],
 "documents":[{"id":"vd1","vehicle_id":"v1","document_type_code":"VEHICLE_REGISTRATION","status":"PENDING","expires_on":null,
   "rejection_reason":null,"uploaded_at":"2026-09-14T09:56:21-04:00","reviewed_at":null,"is_current":true}],
 "vehicle_status":"PENDING","can_carry":false}
"""#

private let supportJSON = #"""
{"tickets":[{"id":"k1","reference":"TKT-2026-000002","category_code":"SAFETY","subject":"SAFETY","status":"OPEN",
  "is_urgent":true,"trip_id":null,"booking_id":null,"created_at":"2026-08-29T18:45:32.468890-04:00","resolved_at":null,
  "messages":[
   {"id":"m1","author_role":"DRIVER","is_from_reporter":true,"body":"راننده از مسیر عادی خارج شد","is_internal":false,"sent_at":"2026-08-29T18:45:32.470754-04:00"},
   {"id":"m2","author_role":"ADMIN","is_from_reporter":false,"body":"Called him.","is_internal":true,"sent_at":"2026-08-29T19:00:00-04:00"}]}],
 "open":13,"urgent_open":2}
"""#

private let unassignedJSON = #"""
{"success":true,"data":[{"id":"t2","number":"VLR-2026-000047","status":"SCHEDULED","ride_kind":"SHARED",
  "scheduled_departure_at":"2026-09-15T04:00:00+00:00","minutes_to_departure":-12,"at_risk":true,
  "origin_station_id":"s1","origin_station_name":"ایستگاه بابر","destination_id":"x1","destination_name":null,
  "seat_capacity":4,"seats_available":2,"booked_seats":2,"open_offers":3,
  "offers_expire_at":"2026-09-15T04:10:00+00:00","offers_expire_in_minutes":8,"candidates":0}],
 "message":null,"meta":{"count":1,"at_risk":1,"drivers_available":3}}
"""#

@Suite("The operations console's shapes")
struct AdminModelTests {
    @Test func theDashboardReadsEverySection() throws {
        let snapshot = try decode(DashboardSnapshot.self, dashboardJSON)
        #expect(snapshot.attention.overdueTrips == 11)
        #expect(snapshot.attention.openTickets == 13)
        #expect(snapshot.attention.total == 11 + 2 + 13 + 7)
        #expect(snapshot.live.moving == 2)
        #expect(snapshot.today.utilisationPercent == 25)
        #expect(snapshot.drivers.withoutFix == 7)
        #expect(snapshot.finance.cashOwed == Money(amountMinor: 70560))
        #expect(snapshot.network.villagesWithoutCoordinates == 372)
        #expect(snapshot.people.passengers == 63)
        #expect(snapshot.history?.days.map(\.id) == ["2026-09-09", "2026-09-10"])
        #expect(snapshot.history?.days.last?.revenueMinor == 62200)
        #expect(snapshot.apps?.latest?.passenger == nil)
        #expect(snapshot.apps?.latest?.driver?.versionName == "1.2.3")
        #expect(snapshot.apps?.versions.map(\.id) == ["driver:android:6", "driver:ios:2"])
        #expect(snapshot.generated != nil)
    }

    @Test func aServerWithoutTheWeekOrTheAppsStillOpensTheDashboard() throws {
        var object = try #require(try JSONSerialization.jsonObject(with: Data(dashboardJSON.utf8)) as? [String: Any])
        object["history"] = nil
        object["apps"] = nil
        object["today"] = ["trips": 0, "bookings": 0, "completed_trips": 0, "cancellations": 0,
                           "seats_capacity": 0, "seats_sold": 0, "utilisation_percent": NSNull()]
        let data = try JSONSerialization.data(withJSONObject: object)
        let snapshot = try APIClient.decoder().decode(DashboardSnapshot.self, from: data)
        #expect(snapshot.history == nil)
        #expect(snapshot.apps == nil)
        // Nothing on offer is not 0% sold.
        #expect(snapshot.today.utilisationPercent == nil)
    }

    @Test func theLiveMapKeepsTheServersStaleVerdictAndReadsANumericTripNumber() throws {
        let map = try decode(LiveMap.self, liveMapJSON)
        #expect(map.staleAfterSeconds == 300)
        #expect(map.drivers.count == 3)
        let first = map.drivers[0]
        #expect(first.location?.stale == true)
        #expect(first.location?.headingDegrees == 90)
        #expect(first.vehicle?.makeAndModel == "Toyota Corolla")
        #expect(first.trip == nil)
        let second = map.drivers[1]
        #expect(second.isOnTrip)
        #expect(second.rehearsing)
        #expect(second.trip?.number == "46")
        #expect(second.trip?.status == .inTransit)
        #expect(second.location?.headingDegrees == nil)
        #expect(second.location?.recorded != nil)
        #expect(map.drivers[2].location == nil)
        #expect(map.drivers[2].phone == nil)
    }

    @Test func aTripsPageKeepsItsTotal() throws {
        let page = try decode(MetaEnvelope<[AdminTrip]>.self, tripsJSON)
        let trips = try #require(page.data)
        #expect(trips.map(\.status) == [.completed, .scheduled])
        #expect(trips[0].departure == ISODate.parse("2026-09-15T02:30:00Z"))
        #expect(trips[0].hasDriver)
        #expect(!trips[1].hasDriver)
        #expect(page.meta?.total == 46)
        let paged = Paged(value: trips, meta: try #require(page.meta))
        #expect(paged.hasMore)
        #expect(paged.nextOffset == 2)
    }

    @Test func theDispatchBoardReadsItsCountsFromTheMeta() throws {
        let page = try decode(MetaEnvelope<[UnassignedTrip]>.self, unassignedJSON)
        let trip = try #require(page.data?.first)
        #expect(trip.atRisk)
        #expect(trip.isPastDeparture)
        #expect(trip.candidates == 0)
        #expect(trip.offersExpireInMinutes == 8)
        #expect(trip.destinationName == nil)
        #expect(page.meta?.atRisk == 1)
        #expect(page.meta?.driversAvailable == 3)
        #expect(Paged(value: [trip], meta: try #require(page.meta)).hasMore == false)
    }

    @Test func aPayoutInTheQueueNamesTheDriverAndWhatCanHappenNext() throws {
        let settlement = try #require(try decode([AdminSettlement].self, settlementsJSON).first)
        #expect(settlement.direction == .collection)
        #expect(settlement.status == .pending)
        #expect(settlement.amount == Money(amountMinor: 25000))
        #expect(settlement.driverName == "محمد")
        #expect(settlement.nextSteps == [.processing, .rejected])
        #expect(settlement.paid == nil)
    }

    @Test func debtorsAreKeyedByDriver() throws {
        let debtors = try decode([Debtor].self, debtorsJSON)
        #expect(debtors.map(\.id) == ["d1", "d2"])
        #expect(debtors[0].amountOwed == Money(amountMinor: 66560))
        #expect(debtors[1].driverName == nil)
    }

    @Test func aDriversPapersForReviewReadAsTheDriversOwnChecklist() throws {
        let checklist = try decode(DocumentChecklist.self, driverDocumentsJSON)
        #expect(checklist.missing == ["LICENSE"])
        #expect(!checklist.canWork)
        #expect(checklist.approvalStatus == .pending)
        #expect(checklist.current("LICENSE")?.status == .rejected)
        #expect(checklist.current("LICENSE")?.rejectionReason == "blurry")
        #expect(checklist.current("NATIONAL_ID")?.expiresOn == "2027-03-20")
        #expect(checklist.current("NATIONAL_ID")?.status.tone == .active)
    }

    @Test func aCarsPapersForReview() throws {
        let checklist = try decode(VehicleChecklist.self, vehicleDocumentsJSON)
        #expect(checklist.plateNumber == "PRW 88 12")
        #expect(checklist.vehicleStatus == .pending)
        #expect(checklist.current("VEHICLE_REGISTRATION")?.status == .pending)
        #expect(!checklist.canCarry)
    }

    @Test func theSupportQueueKeepsInternalNotesApart() throws {
        let queue = try decode(SupportQueue.self, supportJSON)
        #expect(queue.open == 13)
        #expect(queue.urgentOpen == 2)
        let ticket = try #require(queue.tickets.first)
        #expect(ticket.isUrgent)
        #expect(ticket.categoryKey == "ticket.category.safety")
        #expect(ticket.messages.map(\.isInternal) == [false, true])
        #expect(ticket.messages[0].isFromReporter == true)
        #expect(ticket.nextSteps == [.inProgress, .resolved, .closed])
        #expect(ticket.canReply)
    }

    @Test func aWaitingPassengerAndTheOffersMade() throws {
        let request = try decode(AdminRideRequest.self, #"""
        {"passenger_phone":"+93700000800","offer_count":1,"id":"r1","status":"OPEN","origin_station_id":"s1",
         "origin_station_name":"ایستگاه بابر","destination_id":"x1","destination_name":"چاریکار","passenger_count":2,
         "offered_fare":{"amount_minor":30000,"currency":"AFN"},"return_fare":null,"agreed_fare":null,"note":null,
         "requested_for":"2026-09-15T02:30:00+00:00","return_for":null,"expires_at":"2026-09-15T04:00:00+00:00",
         "created_at":"2026-09-15T01:00:00+00:00","trip_id":null,"booking_id":null,"passenger_name":"مریم",
         "offers":[{"id":"o1","ride_request_id":"r1","driver_id":"d1","amount":{"amount_minor":35000,"currency":"AFN"},
           "return_amount":null,"status":"OFFERED","note":null,"created_at":"2026-09-15T01:05:00+00:00",
           "driver_name":"محمد","driver_rating":4.8,"driver_trips":17,"vehicle_plate":"PRW-1234","vehicle_description":"Toyota Corolla"}]}
        """#)
        #expect(!request.isUnanswered)
        #expect(request.offers.first?.amount == Money(amountMinor: 35000))
        #expect(request.offers.first?.driverTrips == 17)
        #expect(request.travelsAt != nil)
    }

    @Test func theRestOfTheListsDecode() throws {
        let booking = try decode(AdminBooking.self, #"""
        {"id":"b1","number":"BKG-2026-000036","trip_number":"VLR-2026-000046","passenger_name":null,
         "passenger_phone":"+93700000988","status":"NO_SHOW","seat_count":1,"fare_total_minor":62200,
         "fare_currency":"AFN","payment_method":"CASH","payment_status":null,"created_at":"2026-09-14T09:56:03.044750-04:00"}
        """#)
        #expect(booking.fare == Money(amountMinor: 62200))
        #expect(booking.status == .noShow)
        #expect(booking.paymentStatus == nil)

        let driver = try decode(AdminDriver.self, #"""
        {"id":"d1","user_id":"u1","full_name":"گل احمد نیازی","phone":null,"approval_status":"APPROVED","availability":"ON_TRIP",
         "rating_average":null,"rating_count":0,"completed_trips":0,"plate_number":null,"vehicle_status":null,"location_age_seconds":42}
        """#)
        #expect(driver.isWorking)
        #expect(driver.locationAgeSeconds == 42)

        let pending = try decode(PendingVehicle.self, #"""
        {"id":"v1","vehicle_type_code":"SEDAN","plate_number":"PRW-4477","seat_capacity":4,"brand":"Toyota","model":"Hiace",
         "year":null,"colour":"سفید","status":"PENDING","driver_id":"d1","driver_name":null,"driver_phone":"+93700000043",
         "driver_approval_status":"APPROVED"}
        """#)
        #expect(pending.year == nil)
        #expect(pending.driverApprovalStatus == .approved)

        let user = try decode(AdminUser.self, #"""
        {"id":"u1","phone":null,"full_name":null,"status":"DEACTIVATED","locale":"fa-AF","roles":["DISPATCHER"],
         "rating_average":null,"rating_count":0,"created_at":"2026-09-14T09:56:21.106586-04:00","last_seen_at":null}
        """#)
        #expect(user.status == .deactivated)
        #expect(user.isStaff)
        #expect(user.lastSeen == nil)

        let finance = try decode(FinanceSummary.self, #"""
        {"period_start":"2026-08-16","period_end":"2026-09-15","gross_minor":905600,"platform_minor":90560,"driver_minor":815040,
         "currency":"AFN","completed_bookings":18,"cash_minor":905600,"online_minor":0,"pending_settlement_minor":-70560,
         "paid_settlement_minor":100000}
        """#)
        #expect(finance.pendingSettlement == Money(amountMinor: -70560))
        #expect(finance.gross.amountMinor == finance.platform.amountMinor + finance.driver.amountMinor)

        let entry = try decode(AuditEntry.self, #"""
        {"id":"a1","occurred_at":"2026-09-14T22:44:26.038603-04:00","actor_id":null,"actor_name":null,"actor_role":"SYSTEM",
         "action":"trip.expired","entity_type":"trip","entity_id":"t1","before":{"status":"SCHEDULED"},
         "after":{"status":"EXPIRED","seats":4},"origin":"api"}
        """#)
        #expect(entry.before?["status"] == .string("SCHEDULED"))
        #expect(entry.after?["seats"] == .int(4))
        #expect(entry.occurred != nil)
    }

    @Test func theDashboardReadsThePassengersBlockAndTheWeeksSignUps() throws {
        var object = try #require(try JSONSerialization.jsonObject(with: Data(dashboardJSON.utf8)) as? [String: Any])
        object["passengers"] = ["total": 63, "new_today": 2, "new_7d": 9, "active_7d": 14, "active_30d": 31,
                                "repeat_30d": 6, "suspended": 1, "with_open_request": 3]
        object["history"] = ["currency": "AFN", "days": [
            ["date": "2026-09-14", "trips": 0, "bookings": 0, "completed_trips": 0, "cancellations": 0,
             "revenue_minor": 0, "commission_minor": 0, "new_passengers": 4, "new_drivers": 1],
        ]]
        let snapshot = try APIClient.decoder().decode(DashboardSnapshot.self, from: JSONSerialization.data(withJSONObject: object))
        let passengers = try #require(snapshot.passengers)
        #expect(passengers == DashboardSnapshot.Passengers(
            total: 63, newToday: 2, new7d: 9, active7d: 14, active30d: 31, repeat30d: 6, suspended: 1, withOpenRequest: 3
        ))
        #expect(snapshot.history?.days.first?.newPassengers == 4)
        #expect(snapshot.history?.days.first?.newDrivers == 1)
    }

    @Test func todaysServerWithoutThePassengerFieldsStillOpensEverything() throws {
        let snapshot = try decode(DashboardSnapshot.self, dashboardJSON)
        #expect(snapshot.passengers == nil)
        #expect(snapshot.history?.days.allSatisfy { $0.newPassengers == nil && $0.newDrivers == nil } == true)

        // A block with a field missing or mistyped costs that figure, not the dashboard.
        var object = try #require(try JSONSerialization.jsonObject(with: Data(dashboardJSON.utf8)) as? [String: Any])
        object["passengers"] = ["total": 63, "new_today": "two"]
        let partial = try APIClient.decoder().decode(DashboardSnapshot.self, from: JSONSerialization.data(withJSONObject: object))
        #expect(partial.passengers?.total == 63)
        #expect(partial.passengers?.newToday == 0)
        #expect(partial.passengers?.withOpenRequest == 0)
    }

    @Test func aPassengersPageReadsHisHistory() throws {
        let detail = try decode(UserDetail.self, #"""
        {"user":{"id":"u7","phone":"+93793817977","full_name":"مریم","status":"SUSPENDED","locale":"ps",
                 "roles":["PASSENGER","DRIVER"],"rating_average":4.5,"rating_count":2,
                 "created_at":"2026-08-01T10:00:00+00:00","last_seen_at":"2026-09-14T22:00:00+04:30"},
         "driver_id":"d7",
         "passenger":{"bookings_total":12,"bookings_completed":9,"bookings_cancelled":2,"no_shows":1,"seats_booked":15,
                      "spent_minor":540000,"currency":"AFN","first_booking_at":"2026-08-02T08:00:00+00:00",
                      "last_booking_at":null,"ride_requests_total":4,"open_ride_requests":1,"tickets_total":3,"tickets_open":1}}
        """#)
        #expect(detail.user.status == .suspended)
        #expect(detail.user.isPassenger && detail.user.isDriver && !detail.user.isStaff)
        #expect(detail.user.lastSeen != nil)
        #expect(detail.driverId == "d7")
        let summary = try #require(detail.passenger)
        #expect(summary.bookingsTotal == 12)
        #expect(summary.noShows == 1)
        #expect(summary.spent == Money(amountMinor: 540000))
        #expect(summary.firstBooking != nil)
        #expect(summary.lastBooking == nil)
        #expect(summary.openRideRequests == 1)
        #expect(summary.ticketsOpen == 1)

        let bare = try decode(UserDetail.self, #"""
        {"user":{"id":"u8","phone":null,"full_name":null,"status":"ACTIVE","locale":"fa-AF","roles":["PASSENGER"],
                 "rating_average":null,"rating_count":0,"created_at":null,"last_seen_at":null},
         "driver_id":null,"passenger":{"bookings_total":1}}
        """#)
        #expect(bare.driverId == nil)
        #expect(bare.passenger?.bookingsTotal == 1)
        #expect(bare.passenger?.ticketsTotal == 0)
        #expect(bare.passenger?.currency == "AFN")
        #expect(try decode(UserDetail.self, #"{"user":{"id":"u9","phone":null,"full_name":null,"status":"ACTIVE","locale":"en","roles":[],"rating_average":null,"rating_count":0,"created_at":null,"last_seen_at":null}}"#).passenger == nil)
    }

    @Test func rowsNameThePassengerOrReporterWhenTheServerSaysWho() throws {
        let booking = try decode(AdminBooking.self, #"""
        {"id":"b2","number":"BKG-2026-000037","trip_number":"VLR-2026-000046","trip_id":"t1","passenger_id":"u7",
         "passenger_name":"مریم","passenger_phone":"+93793817977","status":"COMPLETED","seat_count":2,
         "fare_total_minor":62200,"fare_currency":"AFN","payment_method":"CASH","payment_status":"COLLECTED",
         "created_at":"2026-09-14T09:56:03-04:00"}
        """#)
        #expect(booking.passengerId == "u7")

        var ticketObject = try #require(
            (try JSONSerialization.jsonObject(with: Data(supportJSON.utf8)) as? [String: Any])?["tickets"] as? [[String: Any]]
        ).first!
        #expect(try APIClient.decoder().decode(AdminTicket.self, from: JSONSerialization.data(withJSONObject: ticketObject)).reporterId == nil)
        ticketObject["reporter_id"] = "u7"
        ticketObject["reporter_name"] = "مریم"
        ticketObject["reporter_phone"] = NSNull()
        let ticket = try APIClient.decoder().decode(AdminTicket.self, from: JSONSerialization.data(withJSONObject: ticketObject))
        #expect(ticket.reporterId == "u7")
        #expect(ticket.reporterName == "مریم")
        #expect(ticket.reporterPhone == nil)

        let request = try decode(AdminRideRequest.self, #"""
        {"id":"r2","status":"OPEN","origin_station_id":"s1","origin_station_name":null,"destination_id":"x1",
         "destination_name":null,"passenger_count":1,"offered_fare":{"amount_minor":30000,"currency":"AFN"},
         "return_fare":null,"agreed_fare":null,"note":null,"requested_for":"2026-09-15T02:30:00+00:00","return_for":null,
         "expires_at":"2026-09-15T04:00:00+00:00","created_at":"2026-09-15T01:00:00+00:00","trip_id":null,"booking_id":null,
         "offers":[],"passenger_id":"u7","passenger_name":null,"passenger_phone":null,"offer_count":0}
        """#)
        #expect(request.passengerId == "u7")
        #expect(request.isUnanswered)
    }

    @Test func anOldServersMissingPathIsNotAnUnknownPassenger() {
        #expect(APIClient.error(from: Data(#"{"detail":"Not Found"}"#.utf8), status: 404).isEndpointMissing)
        // What the server really answers for a path it does not have (ui/api/errors.py).
        let missing = #"{"success":false,"error":{"code":"VALIDATION_FAILED","context":{"detail":"Not Found"},"request_id":"r2"}}"#
        #expect(APIClient.error(from: Data(missing.utf8), status: 404).isEndpointMissing)
        let unknown = APIClient.error(from: Data(#"{"success":false,"error":{"code":"USER_NOT_FOUND","context":{},"request_id":"r1"}}"#.utf8), status: 404)
        #expect(unknown.code == "USER_NOT_FOUND")
        #expect(!unknown.isEndpointMissing)
        #expect(!APIError.offline.isEndpointMissing)
    }

    @Test func anExpiryDayIsTheKabulDay() throws {
        // 23:00 UTC on the 10th is already the 11th in Kabul (+04:30).
        let late = try #require(ISODate.parse("2026-09-10T23:00:00Z"))
        #expect(ISODate.formatDay(late) == "2026-09-11")
    }
}

@Suite("Who may do what")
struct StaffAccessTests {
    @Test func aPassengerOrADriverIsNotStaff() {
        #expect(!StaffAccess(roles: ["PASSENGER"]).isStaff)
        #expect(!StaffAccess(roles: ["PASSENGER", "DRIVER"]).isStaff)
        #expect(!StaffAccess.isStaff([]))
    }

    @Test func eachRoleOpensWhatItsServerDependencyOpens() {
        let finance = StaffAccess(roles: ["FINANCE_MANAGER", "PASSENGER"])
        #expect(finance.isStaff && finance.isFinance)
        #expect(!finance.isOperations && !finance.isSupport && !finance.isAdmin)

        let dispatcher = StaffAccess(roles: ["DISPATCHER"])
        #expect(dispatcher.isOperations)
        #expect(!dispatcher.isFinance && !dispatcher.isSupport)

        let support = StaffAccess(roles: ["SUPPORT_AGENT"])
        #expect(support.isSupport)
        #expect(!support.isOperations)

        let owner = StaffAccess(roles: ["SUPER_ADMIN"])
        #expect(owner.isOperations && owner.isFinance && owner.isSupport && owner.isAdmin)
        #expect(owner.staffRoles == [.superAdmin])
        #expect(StaffRole.operationsManager.messageKey == "role.operations_manager")
    }
}

@Suite("Operations console endpoints")
struct AdminEndpointTests {
    @Test func aStaffCodeIsAskedForAsTheConsole() throws {
        let endpoint = API.requestStaffOtp(phone: "0700000001", locale: .dari, channel: API.channelEmail)
        #expect(endpoint.method == .post)
        #expect(endpoint.path == "auth/otp/request")
        #expect(!endpoint.authenticated)
        let json = try body(endpoint)
        #expect(json["audience"] as? String == "staff")
        #expect(json["channel"] as? String == "email")
        #expect(json["locale"] as? String == "fa-AF")
        #expect(json["phone"] as? String == "0700000001")
    }

    @Test func readsAreGetsOnTheRoutersPaths() {
        #expect(AdminAPI.dashboard().path == "admin/dashboard")
        #expect(AdminAPI.liveMap().path == "admin/live-map")
        #expect(AdminAPI.liveMap().method == .get)
        #expect(AdminAPI.pendingVehicles().path == "admin/vehicles/pending")
        #expect(AdminAPI.driverDocuments(driverId: "d1").path == "admin/drivers/d1/documents")
        #expect(AdminAPI.vehicleDocuments(vehicleId: "v1").path == "admin/vehicles/v1/documents")
        #expect(AdminAPI.documentFile("doc1").path == "admin/documents/doc1/file")
        #expect(AdminAPI.vehicleDocumentFile("vd1").path == "admin/vehicle-documents/vd1/file")
        #expect(AdminAPI.settlements().path == "admin/settlements")
        #expect(AdminAPI.debtors().path == "admin/settlements/debtors")
        #expect(AdminAPI.ticket("k1").path == "support/tickets/k1")
        #expect(AdminAPI.rideRequests().path == "admin/ride-requests")
        #expect(query(AdminAPI.finance(days: 7)) == ["days": "7"])
        #expect(query(AdminAPI.unassigned(withinHours: 24)) == ["within_hours": "24"])
        #expect(AdminAPI.unassigned().path == "dispatch/unassigned")
    }

    @Test func tripFiltersAreTheDashboardsCards() {
        let overdue = AdminAPI.trips(TripFilter(overdue: true, limit: 25, offset: 50))
        #expect(overdue.path == "admin/trips")
        #expect(query(overdue) == ["overdue": "true", "limit": "25", "offset": "50"])
        let soon = AdminAPI.trips(TripFilter(status: .scheduled, activeOnly: true, departingWithinHours: 2))
        #expect(query(soon) == ["status": "SCHEDULED", "active_only": "true", "departing_within_hours": "2", "limit": "50", "offset": "0"])
        #expect(query(AdminAPI.drivers(staleGPS: true)) == ["stale_gps": "true", "limit": "100", "offset": "0"])
        #expect(query(AdminAPI.drivers(approvalStatus: .pending)) == ["approval_status": "PENDING", "limit": "100", "offset": "0"])
        // Searched by the server past the first page; blank asks nothing.
        #expect(query(AdminAPI.drivers(search: " 0700 ")) == ["search": "0700", "limit": "100", "offset": "0"])
        #expect(query(AdminAPI.drivers(search: "  ")) == ["limit": "100", "offset": "0"])
        #expect(query(AdminAPI.vehicles(search: "KBL 4521", limit: 50)) == ["search": "KBL 4521", "limit": "50", "offset": "0"])
        #expect(query(AdminAPI.audit(actorId: "u1")) == ["actor_id": "u1", "limit": "50", "offset": "0"])
        #expect(query(AdminAPI.trips(TripFilter(number: "VLR-2026-000047")))["number"] == "VLR-2026-000047")
        #expect(query(AdminAPI.bookings(status: .noShow, tripId: "t1")) == ["status": "NO_SHOW", "trip_id": "t1", "limit": "50", "offset": "0"])
        #expect(query(AdminAPI.audit(entityType: "driver")) == ["entity_type": "driver", "limit": "50", "offset": "0"])
    }

    @Test func approvalRecordsTheNameOnlyWhenOneIsGiven() throws {
        let named = AdminAPI.approveDriver("d1", fullName: "  گل احمد  ")
        #expect(named.method == .post)
        #expect(named.path == "admin/drivers/d1/approve")
        #expect(try body(named)["full_name"] as? String == "گل احمد")
        // A blank name keeps the one on record rather than erasing it.
        #expect(try body(AdminAPI.approveDriver("d1", fullName: " ")).isEmpty)
        let suspend = AdminAPI.suspendDriver("d1", reason: "No licence")
        #expect(suspend.path == "admin/drivers/d1/suspend")
        #expect(try body(suspend)["reason"] as? String == "No licence")
        // The body is required even without a reason: an object, not nothing.
        #expect(try body(AdminAPI.suspendDriver("d1", reason: nil)).isEmpty)
    }

    @Test func aRejectedPaperCarriesItsReasonAndAVerifiedOneItsExpiry() throws {
        let rejected = AdminAPI.reviewDocument("doc1", verified: false, rejectionReason: "blurry")
        #expect(rejected.path == "admin/documents/doc1/review")
        let json = try body(rejected)
        #expect(json["verified"] as? Bool == false)
        #expect(json["rejection_reason"] as? String == "blurry")
        #expect(json["expires_on"] == nil)
        let verified = AdminAPI.reviewVehicleDocument("vd1", verified: true, expiresOn: "2027-03-20")
        #expect(verified.path == "admin/vehicle-documents/vd1/review")
        #expect(try body(verified)["expires_on"] as? String == "2027-03-20")
        #expect(try body(verified)["verified"] as? Bool == true)
    }

    @Test func decisionsPostTheBodiesTheRoutersRead() throws {
        let vehicle = AdminAPI.decideVehicle("v1", approve: false, reason: "Brakes")
        #expect(vehicle.path == "admin/vehicles/v1/decide")
        #expect(try body(vehicle)["approve"] as? Bool == false)
        #expect(try body(vehicle)["reason"] as? String == "Brakes")

        let paid = AdminAPI.decideSettlement("s1", to: .paid)
        #expect(paid.path == "admin/settlements/s1/decide")
        #expect(try body(paid).mapValues { "\($0)" } == ["to": "PAID"])

        let collect = AdminAPI.collect(driverId: "d1")
        #expect(collect.path == "admin/settlements/collect")
        #expect(try body(collect).mapValues { "\($0)" } == ["driver_id": "d1"])
        #expect(try body(AdminAPI.collect(driverId: "d1", amountMinor: 25000))["amount_minor"] as? Int == 25000)

        let offer = AdminAPI.offerTrip("t1")
        #expect(offer.method == .post)
        #expect(offer.path == "dispatch/trips/t1/offer")
        #expect(offer.idempotencyKey == nil)
    }

    @Test func supportIsReadAndAnsweredWhereThePanelDoes() throws {
        #expect(query(AdminAPI.supportTickets()) == ["limit": "50"])
        #expect(query(AdminAPI.supportTickets(.all)) == ["status": "ALL", "limit": "50"])
        #expect(query(AdminAPI.supportTickets(.only(.inProgress), category: "SAFETY")) == ["status": "IN_PROGRESS", "category": "SAFETY", "limit": "50"])
        let decide = AdminAPI.decideTicket("k1", status: .resolved)
        #expect(decide.path == "admin/support/tickets/k1/decide")
        #expect(try body(decide)["status"] as? String == "RESOLVED")
        let note = AdminAPI.replyToTicket("k1", body: " Called him. ", isInternal: true)
        #expect(note.path == "support/tickets/k1/messages")
        #expect(try body(note)["body"] as? String == "Called him.")
        #expect(try body(note)["is_internal"] as? Bool == true)
    }

    @Test func accountsAreFoundByDigitsAndSwitchedByPath() throws {
        #expect(query(AdminAPI.users(phone: "۰۷۹۳ ۸۱۷", status: .suspended)) == ["phone": "0793 817", "status": "SUSPENDED", "limit": "50"])
        #expect(query(AdminAPI.users(phone: "  ")) == ["limit": "50"])
        #expect(AdminAPI.suspendUser("u1", reason: "troll").path == "admin/users/u1/suspend")
        #expect(AdminAPI.reinstateUser("u1").path == "admin/users/u1/reinstate")
        #expect(try body(AdminAPI.reinstateUser("u1")).isEmpty)
    }

    @Test func thePassengerDirectoryAsksByRoleSearchAndPage() throws {
        let page = AdminAPI.users(role: .passenger, search: " ۰۷۹۳ ", status: .active, limit: 50, offset: 100)
        #expect(page.method == .get)
        #expect(page.path == "admin/users")
        #expect(query(page) == ["role": "PASSENGER", "search": "۰۷۹۳", "status": "ACTIVE", "limit": "50", "offset": "100"])
        // Blank asks nothing; the server's bounds are kept on this side too.
        #expect(query(AdminAPI.users(role: nil, search: "  ", limit: 500, offset: -3)) == ["limit": "200", "offset": "0"])
        #expect(query(AdminAPI.users(role: .staff))["role"] == "STAFF")

        let one = AdminAPI.user("u7")
        #expect(one.method == .get)
        #expect(one.path == "admin/users/u7")
        #expect(AdminAPI.suspendUser("u7", reason: " no-shows ").path == "admin/users/u7/suspend")
        #expect(try body(AdminAPI.suspendUser("u7", reason: " no-shows "))["reason"] as? String == "no-shows")
        #expect(try body(AdminAPI.reinstateUser("u7", reason: "spoke to him"))["reason"] as? String == "spoke to him")
    }

    @Test func onePassengersBookingsTicketsAndRequestsAreAskedForByHisId() {
        #expect(query(AdminAPI.bookings(passengerId: "u7", limit: 20)) == ["passenger_id": "u7", "limit": "20", "offset": "0"])
        #expect(query(AdminAPI.supportTickets(.all, reporterId: "u7", limit: 50)) == ["status": "ALL", "reporter_id": "u7", "limit": "50"])
        #expect(query(AdminAPI.rideRequests(passengerId: "u7")) == ["passenger_id": "u7", "limit": "50"])
        // Unchanged without the new filters.
        #expect(query(AdminAPI.rideRequests(limit: 100)) == ["limit": "100"])
        #expect(query(AdminAPI.bookings()) == ["limit": "50", "offset": "0"])
    }
}

// MARK: - The client's two new ways to read an answer

/// Its own stub, so these requests never race the other suite's handler.
final class AdminStub: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var handler: (@Sendable (URLRequest) -> (Int, [String: String], Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        guard let (status, headers, body) = Self.handler?(request) else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: headers)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }
}

private final class Counter: @unchecked Sendable {
    private let lock = NSLock()
    private var values: [String: Int] = [:]
    func bump(_ key: String) -> Int { lock.withLock { values[key, default: 0] += 1; return values[key]! } }
}

@Suite(.serialized) struct AdminClientTests {
    private func client(_ store: SessionStore) -> APIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [AdminStub.self]
        return APIClient(
            baseURL: URL(string: "http://test.invalid/api/v1/")!,
            store: store,
            transport: URLSession(configuration: configuration)
        )
    }

    private func store() -> MemorySessionStore {
        MemorySessionStore(SessionDTO(
            userId: "u1", accessToken: "old", refreshToken: "r1",
            roles: ["SUPER_ADMIN"], isNewUser: false, expiresInSeconds: 900
        ))
    }

    @Test func aListKeepsItsTotal() async throws {
        AdminStub.handler = { _ in (200, ["Content-Type": "application/json"], Data(tripsJSON.utf8)) }
        let page = try await client(store()).sendWithMeta(AdminAPI.trips()).get()
        #expect(page.items.count == 2)
        #expect(page.meta.total == 46)
        #expect(page.hasMore)
    }

    @Test func aDocumentIsFetchedWithTheTokenRenewedOnceOnTheWay() async throws {
        let counter = Counter()
        let photo = Data([0xFF, 0xD8, 0xFF, 0xE0, 0x00])
        AdminStub.handler = { request in
            let path = request.url?.path ?? ""
            if path.hasSuffix("auth/refresh") {
                _ = counter.bump("refresh")
                let renewed = #"{"success":true,"data":{"user_id":"u1","access_token":"new","refresh_token":"r2","roles":["SUPER_ADMIN"],"is_new_user":false,"expires_in_seconds":900}}"#
                return (200, ["Content-Type": "application/json"], Data(renewed.utf8))
            }
            if request.value(forHTTPHeaderField: "Authorization") != "Bearer new" {
                let expired = #"{"success":false,"error":{"code":"TOKEN_EXPIRED","context":{},"request_id":"r1"}}"#
                return (401, ["Content-Type": "application/json"], Data(expired.utf8))
            }
            return (200, ["Content-Type": "image/jpeg", "Cache-Control": "no-store, private"], photo)
        }
        let sessions = store()
        let file = try await client(sessions).download(AdminAPI.documentFile("doc1")).get()
        #expect(file.data == photo)
        #expect(file.contentType == "image/jpeg")
        #expect(file.isImage && !file.isPDF)
        #expect(counter.bump("refresh") == 2)  // exactly one refresh happened before this bump
        #expect(sessions.accessToken == "new")

        let bytes = try await client(sessions).data(for: AdminAPI.vehicleDocumentFile("vd1")).get()
        #expect(bytes == photo)
    }

    @Test func aMissingFileIsTheServersErrorNotBytes() async {
        AdminStub.handler = { _ in
            let missing = #"{"success":false,"error":{"code":"DOCUMENT_NOT_FOUND","context":{"id":"doc9"},"request_id":"r9"}}"#
            return (404, ["Content-Type": "application/json"], Data(missing.utf8))
        }
        let result = await client(store()).download(AdminAPI.documentFile("doc9"))
        guard case .failure(let error) = result else { Issue.record("expected a failure"); return }
        #expect(error.code == "DOCUMENT_NOT_FOUND")
        #expect(error.requestId == "r9")
    }
}
