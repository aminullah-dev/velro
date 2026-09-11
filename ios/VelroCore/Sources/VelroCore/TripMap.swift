import Foundation

/// A stretch of road to take care on: a bend, a caution zone, a bazaar.
public struct RoadAlert: Decodable, Sendable, Hashable {
    public let latitude: Double
    public let longitude: Double
    public let radiusM: Int
    public let kind: String
    /// A message key -- "road.alert.curve" -- never a sentence.
    public let messageKey: String

    public init(latitude: Double, longitude: Double, radiusM: Int, kind: String = "curve", messageKey: String) {
        self.latitude = latitude
        self.longitude = longitude
        self.radiusM = radiusM
        self.kind = kind
        self.messageKey = messageKey
    }
}

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
    /// Every advisory in the region; `RoadAhead` picks the ones on this road.
    public let alerts: [RoadAlert]?
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

/// The next warning on the road, and how far it is -- the Android `RoadAhead`.
///
/// What the top of the full-screen trip map says on both phones: "Sharp bends
/// ahead -- 2 km away", or the warning itself once they are in it. Walked
/// along the road like `Eta`, and only advisories on this road and ahead of
/// the car count: the server sends the whole region's.
public enum RoadAhead {
    public struct Next: Equatable, Sendable {
        public let messageKey: String
        public let metres: Int
        public let inside: Bool
    }

    static let onRoadSlackMetres = 300.0

    public static func next(
        road: [(latitude: Double, longitude: Double)],
        car: (latitude: Double, longitude: Double),
        alerts: [RoadAlert]
    ) -> Next? {
        // Inside a zone: that zone, whatever the road knows.
        let inside = alerts
            .map { ($0, Eta.distance(car, ($0.latitude, $0.longitude))) }
            .filter { $0.1 <= Double($0.0.radiusM) }
            .min { $0.1 < $1.1 }
        if let (alert, _) = inside { return Next(messageKey: alert.messageKey, metres: 0, inside: true) }

        guard road.count >= 2 else { return nil }
        let (carIndex, carSnap) = nearest(road, car)
        guard carSnap <= Eta.maxSnapMetres else { return nil }

        var along = [0.0]
        for index in 1..<road.count { along.append(along[index - 1] + Eta.distance(road[index - 1], road[index])) }

        var best: Next?
        for alert in alerts {
            let (index, snap) = nearest(road, (alert.latitude, alert.longitude))
            guard snap <= Double(alert.radiusM) + onRoadSlackMetres, index > carIndex else { continue }
            let ahead = Int(along[index] - along[carIndex])
            if best == nil || ahead < best!.metres { best = Next(messageKey: alert.messageKey, metres: ahead, inside: false) }
        }
        return best
    }

    private static func nearest(
        _ points: [(latitude: Double, longitude: Double)],
        _ target: (latitude: Double, longitude: Double)
    ) -> (Int, Double) {
        var best = (0, Double.greatestFiniteMagnitude)
        for (index, point) in points.enumerated() {
            let d = Eta.distance(point, target)
            if d < best.1 { best = (index, d) }
        }
        return best
    }
}
