import Foundation
import VelroCore

/// The places, cache first.
///
/// Reads come from the saved snapshot, so choosing a village works with no
/// network at all. The network only refreshes it, and the refresh is a 304
/// when the version has not changed -- which it usually has not, because the
/// districts of Ghorband do not move.
@MainActor
final class GeographyStore {
    private(set) var snapshot: GeoSnapshot?
    private let cache: ResponseCache
    private static let key = "geo-snapshot"

    init(cache: ResponseCache) {
        self.cache = cache
        snapshot = cache.value(GeoSnapshot.self, key: Self.key)
    }

    /// nil when the snapshot is current, whether or not anything changed.
    func refresh(using client: APIClient) async -> APIError? {
        switch await client.data(API.geoSnapshot(version: snapshot?.version)) {
        case .success(let data):
            guard let fresh = APIClient.decodeEnvelope(data, as: GeoSnapshot.self) else {
                return .unknown(reason: "response_unreadable")
            }
            cache.store(data, key: Self.key)
            snapshot = fresh
            return nil
        case .failure(let error):
            return error.httpStatus == 304 ? nil : error
        }
    }

    var districts: [District] { (snapshot?.districts ?? []).sorted { $0.code < $1.code } }

    func villages(in districtId: String) -> [Village] {
        (snapshot?.villages ?? []).filter { $0.districtId == districtId }.sorted { $0.name < $1.name }
    }

    /// The village's main station first.
    func stations(in villageId: String) -> [Station] {
        (snapshot?.stations ?? []).filter { $0.villageId == villageId }.sorted { a, b in
            let (ap, bp) = (a.isPrimary ?? false, b.isPrimary ?? false)
            return ap != bp ? ap : a.name < b.name
        }
    }

    /// Where this station can go. Saved per station: it is the screen just
    /// before asking, and a passenger at a roadside should not wait for it.
    func destinations(from stationId: String, using client: APIClient) async -> Result<[DestinationGroup], APIError> {
        let key = "geo-destinations-\(stationId)"
        if let saved = cache.value([DestinationGroup].self, key: key), !saved.isEmpty {
            return .success(saved)
        }
        let result = await client.send(API.destinations(from: stationId), caching: key, in: cache)
        if let groups = result.value { return .success(groups) }
        return .failure(result.error ?? .unknown())
    }
}
