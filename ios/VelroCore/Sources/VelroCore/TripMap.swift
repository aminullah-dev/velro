import Foundation

public struct MapPlace: Decodable, Sendable, Hashable {
    public let name: String
    public let latitude: Double
    public let longitude: Double

    public init(name: String, latitude: Double, longitude: Double) {
        self.name = name
        self.latitude = latitude
        self.longitude = longitude
    }
}

/// The road between a journey's two ends, as the server draws it. Any part
/// may be absent; a screen shows what there is and no more.
public struct TripMap: Decodable, Sendable, Hashable {
    public let origin: MapPlace?
    public let destination: MapPlace?
    /// (latitude, longitude) pairs along the road, or nil when honestly unknown.
    public let geometry: [[Double]]?
    public let stations: [MapPlace]?
    /// The routing engine's average for this road, for honest ETAs.
    public let avgSpeedKmh: Double?
    public let attribution: String?

    public var road: [(latitude: Double, longitude: Double)] {
        (geometry ?? []).compactMap { $0.count >= 2 ? ($0[0], $0[1]) : nil }
    }
}

extension API {
    /// The road a journey would take, previewed before anyone commits to it.
    public static func journeyMap(originStationId: String, destinationId: String) -> Endpoint<TripMap> {
        .get("geo/map/journey", query: [
            URLQueryItem(name: "origin_station_id", value: originStationId),
            URLQueryItem(name: "destination_id", value: destinationId),
        ])
    }
}

/// "Arriving in about N minutes", computed honestly or not at all.
///
/// The distance is walked along the road between the points nearest the car
/// and nearest where it is going; the speed is the routing engine's own average
/// for that road. A car more than three kilometres off the line gets nil, not
/// a guess: a number the screen cannot defend is one it must not show. The
/// Android `Eta`, unchanged.
public enum Eta {
    static let maxSnapMetres = 3_000.0

    public static func minutes(
        road: [(latitude: Double, longitude: Double)],
        car: (latitude: Double, longitude: Double),
        target: (latitude: Double, longitude: Double),
        averageKmh: Double?
    ) -> Int? {
        guard road.count >= 2, let speed = averageKmh, speed > 0 else { return nil }
        let (carIndex, carSnap) = nearest(road, to: car)
        let (targetIndex, targetSnap) = nearest(road, to: target)
        guard carSnap <= maxSnapMetres, targetSnap <= maxSnapMetres else { return nil }
        var metres = 0.0
        for index in min(carIndex, targetIndex)..<max(carIndex, targetIndex) {
            metres += distance(road[index], road[index + 1])
        }
        return Int(metres / 1000 / speed * 60)
    }

    private static func nearest(
        _ points: [(latitude: Double, longitude: Double)],
        to target: (latitude: Double, longitude: Double)
    ) -> (Int, Double) {
        var best = (0, Double.greatestFiniteMagnitude)
        for (index, point) in points.enumerated() {
            let d = distance(point, target)
            if d < best.1 { best = (index, d) }
        }
        return best
    }

    static func distance(_ a: (latitude: Double, longitude: Double), _ b: (latitude: Double, longitude: Double)) -> Double {
        let dx = (a.longitude - b.longitude) * 111_320 * cos((a.latitude + b.latitude) / 2 * .pi / 180)
        let dy = (a.latitude - b.latitude) * 110_574
        return (dx * dx + dy * dy).squareRoot()
    }
}
