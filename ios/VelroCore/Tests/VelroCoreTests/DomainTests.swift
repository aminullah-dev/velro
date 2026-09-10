import Foundation
import Testing
@testable import VelroCore

/// The calendar table the Android app and the admin panel are held to.
@Suite struct CalendarTests {
    private struct Table: Decodable {
        struct Conversion: Decodable { let gregorian: String; let shamsi: [Int] }
        let nowruz: [String: String]
        let conversions: [Conversion]
    }

    private func table() throws -> Table {
        let url = iosRoot.deletingLastPathComponent().appending(path: "docs/domain/calendar.json")
        return try JSONDecoder().decode(Table.self, from: Data(contentsOf: url))
    }

    private func gregorian(_ text: String) -> (Int, Int, Int) {
        let parts = text.split(separator: "-").compactMap { Int($0) }
        return (parts[0], parts[1], parts[2])
    }

    @Test func everyObservedNowruzIsTheFirstOfHamal() throws {
        for (year, date) in try table().nowruz {
            let (y, m, d) = gregorian(date)
            #expect(Calendars.shamsi(year: y, month: m, day: d) == .init(year: Int(year)!, month: 1, day: 1), "\(date)")
        }
    }

    @Test func everyListedConversionHolds() throws {
        for row in try table().conversions {
            let (y, m, d) = gregorian(row.gregorian)
            let expected = Calendars.ShamsiDate(year: row.shamsi[0], month: row.shamsi[1], day: row.shamsi[2])
            #expect(Calendars.shamsi(year: y, month: m, day: d) == expected, "\(row.gregorian)")
        }
    }

    @Test func datesAreReadInKabulTime() {
        // 21:00 UTC on 11 September is already 01:30 on the 12th in Kabul.
        let late = ISODate.parse("2026-09-11T21:00:00+00:00")!
        #expect(Calendars.time(late, .english) == "01:30")
        #expect(Calendars.date(late, .english) == "12 Sep 2026")
        #expect(Calendars.date(late, .dari) == "۲۱ سنبله ۱۴۰۵")
        #expect(Calendars.date(late, .pashto) == "۲۱ وږی ۱۴۰۵")
    }

    @Test func sixTomorrowIsSixInKabul() {
        let now = ISODate.parse("2026-09-10T10:00:00Z")!  // 14:30 in Kabul
        let six = Calendars.kabul(daysFromToday: 1, hour: 6, now: now)
        #expect(ISODate.format(six) == "2026-09-11T01:30:00Z")
        #expect(Calendars.kabulHour(now) == 14)
    }

    @Test func pythonTimestampsAreRead() {
        #expect(ISODate.parse("2026-09-10T11:05:00.500000+00:00") == ISODate.parse("2026-09-10T11:05:00Z")!.addingTimeInterval(0.5))
        #expect(ISODate.parse("2026-09-10T11:05:00") == ISODate.parse("2026-09-10T11:05:00Z"))
        #expect(ISODate.parse("") == nil)
        #expect(ISODate.parse("not a date") == nil)
    }
}

@Suite struct PlaceNameTests {
    @Test func spellingDoesNotHideAVillage() {
        #expect(PlaceNames.matches("سیاه‌گرد", "سیاهگرد"))
        #expect(PlaceNames.matches("كابل", "کابل"))
        #expect(PlaceNames.matches("قریه ۱۲", "12"))
        #expect(PlaceNames.matches("مُحمّد آغه", "محمداغه"))
    }

    @Test func pashtoLettersAreNotFolded() {
        #expect(!PlaceNames.matches("ډنډ", "دند"))
    }
}

@Suite struct NegotiationRuleTests {
    private func offer(_ out: Int64, back: Int64? = nil, status: String = "OFFERED") -> String {
        let returnPart = back.map { #","return_amount":{"amount_minor":\#($0),"currency":"AFN"}"# } ?? ""
        return #"{"id":"o\#(out)","ride_request_id":"r","driver_id":"d","amount":{"amount_minor":\#(out),"currency":"AFN"}\#(returnPart),"status":"\#(status)"}"#
    }

    private func request(_ offers: [String], back: Int64? = nil) throws -> RideRequest {
        let returnPart = back.map { #","return_fare":{"amount_minor":\#($0),"currency":"AFN"}"# } ?? ""
        let json = #"{"id":"r","status":"OPEN","origin_station_id":"s","destination_id":"x","passenger_count":1,"offered_fare":{"amount_minor":30000,"currency":"AFN"}\#(returnPart),"offers":[\#(offers.joined(separator: ","))]}"#
        return try APIClient.decoder().decode(RideRequest.self, from: Data(json.utf8))
    }

    /// Cheapest journey first, by both legs -- not by the outbound alone.
    @Test func liveOffersAreSortedByTheWholeJourney() throws {
        let asked = try request([offer(30000, back: 40000), offer(35000, back: 30000), offer(20000, status: "WITHDRAWN")], back: 25000)
        #expect(asked.liveOffers.map(\.id) == ["o35000", "o30000"])
        #expect(asked.askingTotal.amountMinor == 55000)
        #expect(asked.liveOffers[0].difference(from: asked.askingTotal) == 10000)
    }

    @Test func anUnknownStatusDoesNotBreakTheList() throws {
        let asked = try request([offer(30000, status: "SOMETHING_NEW")])
        #expect(asked.liveOffers.count == 1)
    }

    @Test func bookingLifecycleMatchesTheServer() {
        #expect(BookingStatus.allCases.filter(\.isTerminal) == [.completed, .cancelled, .noShow])
        #expect(!BookingStatus.onboard.isCancellable)
        #expect(BookingStatus.ready.isCancellable)
    }
}

@Suite struct EtaTests {
    /// A straight road north, a kilometre between points, at 30 km/h.
    private let road: [(latitude: Double, longitude: Double)] = (0...10).map { (34.9 + Double($0) * 0.009044, 68.6) }

    @Test func minutesAreWalkedAlongTheRoad() {
        let minutes = Eta.minutes(road: road, car: road[0], target: road[10], averageKmh: 30)
        #expect(minutes == 19 || minutes == 20)
    }

    @Test func aCarOffTheRoadGetsNoGuess() {
        #expect(Eta.minutes(road: road, car: (35.5, 69.5), target: road[10], averageKmh: 30) == nil)
        #expect(Eta.minutes(road: road, car: road[0], target: road[10], averageKmh: nil) == nil)
    }
}
