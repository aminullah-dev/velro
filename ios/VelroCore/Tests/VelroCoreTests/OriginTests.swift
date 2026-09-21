import Foundation
import Testing
@testable import VelroCore

/// "Where from": when a fix may name the spot, and the recents list (ADR 0015).
@Suite struct OriginTests {
    @Test func aTightFixInsideMayNameTheSpot() {
        #expect(Naming.canName(accuracyM: 25, inside: true))
        #expect(Naming.canName(accuracyM: 300, inside: true))
    }

    /// The server refuses anything vaguer, so the field is not offered.
    @Test func aCoarseOrUnknownFixMayNot() {
        #expect(!Naming.canName(accuracyM: 1_500, inside: true))
        #expect(!Naming.canName(accuracyM: nil, inside: true))
        #expect(!Naming.canName(accuracyM: -1, inside: true))
    }

    @Test func outsideTheAreaNothingIsNamed() {
        #expect(!Naming.canName(accuracyM: 10, inside: false))
    }

    @Test func everyRefusalHasItsOwnSentence() {
        #expect(Naming.refusalKey("personal") == "origin.place.refused.personal")
        #expect(Naming.refusalKey("digits") == "origin.place.refused.digits")
        #expect(Naming.refusalKey("contact") == "origin.place.refused.digits")
        #expect(Naming.refusalKey("generic") == "origin.place.refused.generic")
        #expect(Naming.refusalKey("too_long") == "origin.place.refused.too_long")
        #expect(Naming.refusalKey("rejected") == "origin.place.refused.rejected")
        #expect(Naming.refusalKey("coarse") == "origin.place.need_precise")
    }

    @Test func recentsPutTheLatestFirstAndKeepOneRowPerOrigin() {
        func entry(_ station: String, _ place: String? = nil) -> RecentOrigin {
            RecentOrigin(stationId: station, stationName: station, districtId: "d", placeId: place, placeName: place)
        }
        var list: [RecentOrigin] = []
        list = RecentOrigin.merged(list, with: entry("s1"))
        list = RecentOrigin.merged(list, with: entry("s2", "p2"))
        list = RecentOrigin.merged(list, with: entry("s1"))
        #expect(list.map(\.stationId) == ["s1", "s2"])
        // The same station with a named place is a different origin.
        list = RecentOrigin.merged(list, with: entry("s1", "p1"))
        #expect(list.count == 3)
        for n in 0..<10 { list = RecentOrigin.merged(list, with: entry("x\(n)")) }
        #expect(list.count == RecentOrigin.limit)
    }

    /// Coordinates arrive as decimal text, exactly as the server writes them.
    /// A Double here once made the saved name vanish from the card: the POST
    /// succeeded and the answer could not be read.
    @Test func whereaboutsDecodeFromTheServer() throws {
        let json = """
        {"success": true, "data": {
          "inside": true,
          "district": {"id": "d1", "code": "GRB-SYG", "name": "سیاه‌گرد", "alternative_name": null,
                       "province_id": "p", "latitude": "35.120000", "longitude": "68.780000"},
          "district_source": "centre",
          "stations": [{"id": "s1", "code": "GRB-SYG-001-S1", "name": "ایستگاه خیشکی",
                        "village_id": "v1", "district_id": "d1", "is_primary": true,
                        "description": null, "latitude": "35.120000", "longitude": "68.780000", "distance_m": 420}],
          "places": [{"id": "pl", "name": "قلعه نو", "district_id": "d1", "village_id": "v2",
                      "nearest_station_id": "s1", "latitude": "35.118500", "longitude": "68.790500",
                      "status": "APPROVED", "distance_m": 300}]
        }}
        """
        let here = try #require(APIClient.decodeEnvelope(Data(json.utf8), as: Whereabouts.self))
        #expect(here.inside)
        #expect(here.districtIsGuess)
        #expect(here.stations.first?.distanceM == 420)
        #expect(here.places.first?.isApproved == true)
        #expect(here.places.first?.nearestStationId == "s1")
    }

    @Test func anAskFromHereCarriesThePlace() throws {
        let ask = RideAsk(
            originStationId: "s1", destinationId: "d", passengerCount: 1,
            offeredFareMinor: 30_000, returnFareMinor: nil, note: nil,
            requestedFor: nil, returnFor: nil, latitude: 35.125, longitude: 68.77,
            originPlaceId: "pl"
        )
        let body = try #require(APIClient.encode(ask))
        let text = String(decoding: body, as: UTF8.self)
        #expect(text.contains("\"origin_place_id\":\"pl\""))
    }
}
