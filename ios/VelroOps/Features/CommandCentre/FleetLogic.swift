import Foundation
import MapKit
import VelroCore

// The command centre's rules, apart from its views: what state a car is in,
// which filter it passes, where the service region is. The same reading as
// the web panel's live map (admin/src/components/LiveMap.tsx), so a dot on
// the Mac and a dot in the browser never disagree about a driver.

/// What a car on the map is doing.
///
/// An old fix outranks what the car is doing: grey means "we do not know
/// where this car is now", which is as true of a car on a trip as of one
/// waiting -- more worrying, if anything, and the panel then says so in words.
enum FleetCarState: Int, CaseIterable, Identifiable, Sendable {
    case trip, waiting, stale

    var id: Int { rawValue }

    var labelKey: String {
        switch self {
        case .trip: "admin.map.on_trip"
        case .waiting: "admin.map.online"
        case .stale: "admin.map.stale"
        }
    }

    /// The glyph inside the pin: the state is never the colour alone.
    var symbol: String {
        switch self {
        case .trip: "car.fill"
        case .waiting: "hourglass"
        case .stale: "location.slash.fill"
        }
    }

    /// Drawn last is drawn on top: a car on a trip is never hidden under a
    /// waiting one.
    var drawOrder: Int {
        switch self {
        case .stale: 0
        case .waiting: 1
        case .trip: 2
        }
    }
}

extension LiveDriver {
    var carState: FleetCarState {
        if location?.stale == true { return .stale }
        return isOnTrip ? .trip : .waiting
    }

    /// The glyph a list row or the panel shows: a driver who never sent a
    /// location wears the "location unknown" one, not a waiting car's.
    var glyphState: FleetCarState { location == nil ? .stale : carState }

    var coordinate: CLLocationCoordinate2D? {
        location.map { CLLocationCoordinate2D(latitude: $0.latitude, longitude: $0.longitude) }
    }

    /// Near enough to the region to be a car in service. A phone that never
    /// had a real fix reports wherever its emulator left it -- the development
    /// database has a driver in San Francisco.
    var isInServiceArea: Bool {
        guard let location else { return false }
        return FleetRegion.isNear(latitude: location.latitude, longitude: location.longitude)
    }

    /// The name, or the panel's words for a driver with none on record.
    func displayName(_ strings: Strings) -> String {
        if let name = name?.trimmingCharacters(in: .whitespaces), !name.isEmpty { return name }
        return strings["admin.map.unnamed"]
    }

    /// For VoiceOver: who, what, which car.
    func accessibilitySummary(_ strings: Strings) -> String {
        var parts = [displayName(strings), strings[carState.labelKey]]
        if location?.stale == true { parts.append(strings[isOnTrip ? "admin.map.on_trip" : "admin.map.online"]) }
        if let trip { parts.append(strings["admin.map.trip", ["number": trip.number]]) }
        if let plate = vehicle?.plate { parts.append(plate) }
        if rehearsing { parts.append(strings["admin.map.test_legend"]) }
        return parts.joined(separator: strings.locale.isRTL ? "، " : ", ")
    }
}

/// The chips over the map and the list.
enum FleetFilter: String, CaseIterable, Identifiable, Sendable {
    case all, trip, waiting, stale, test

    var id: String { rawValue }

    var labelKey: String {
        switch self {
        case .all: "admin.filter.all"
        case .trip: "admin.map.on_trip"
        case .waiting: "ops.map.filter.waiting"
        // "Without a fix": old or missing, the dashboard's stale-GPS card.
        case .stale: "admin.filter.stale_gps"
        case .test: "admin.map.test"
        }
    }

    /// A driver with no location at all counts as without a fix, as the
    /// server's `stale_gps_drivers` does; otherwise the pin's own state.
    func matches(_ driver: LiveDriver) -> Bool {
        switch self {
        case .all: true
        case .trip: driver.location == nil ? driver.isOnTrip : driver.carState == .trip
        case .waiting: driver.location == nil ? !driver.isOnTrip : driver.carState == .waiting
        case .stale: driver.location == nil || driver.location?.stale == true
        case .test: driver.rehearsing
        }
    }
}

/// Kabul, Parwan and Ghorband: where the service runs, so where the map opens.
enum FleetRegion {
    static let south = 34.3
    static let north = 35.6
    static let west = 67.9
    static let east = 69.7
    /// How far outside the box a car still counts as in service.
    static let margin = 0.5

    static var region: MKCoordinateRegion {
        MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: (south + north) / 2, longitude: (west + east) / 2),
            span: MKCoordinateSpan(latitudeDelta: (north - south) * 1.08, longitudeDelta: (east - west) * 1.08)
        )
    }

    static func isNear(latitude: Double, longitude: Double) -> Bool {
        latitude >= south - margin && latitude <= north + margin
            && longitude >= west - margin && longitude <= east + margin
    }

    /// The smallest region holding these points, padded, and never closer
    /// than a few streets: one car alone is not fitted down to a doorstep.
    static func fitting(_ coordinates: [CLLocationCoordinate2D]) -> MKCoordinateRegion? {
        guard let first = coordinates.first else { return nil }
        var (minLat, maxLat, minLon, maxLon) = (first.latitude, first.latitude, first.longitude, first.longitude)
        for point in coordinates.dropFirst() {
            minLat = min(minLat, point.latitude)
            maxLat = max(maxLat, point.latitude)
            minLon = min(minLon, point.longitude)
            maxLon = max(maxLon, point.longitude)
        }
        let minimumSpan = 0.03
        return MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: (minLat + maxLat) / 2, longitude: (minLon + maxLon) / 2),
            span: MKCoordinateSpan(
                latitudeDelta: max(minimumSpan, (maxLat - minLat) * 1.5),
                longitudeDelta: max(minimumSpan, (maxLon - minLon) * 1.5)
            )
        )
    }
}

/// A snapshot sorted into what the map can draw and what it cannot.
struct FleetGroups {
    /// A location near the service region: pins on the map.
    let onMap: [LiveDriver]
    /// A location far away: listed, not drawn into the first view.
    let faraway: [LiveDriver]
    /// Never sent a location: listed, or they would be online and nowhere.
    let withoutFix: [LiveDriver]

    init(_ drivers: [LiveDriver]) {
        onMap = drivers.filter { $0.isInServiceArea }
        faraway = drivers.filter { $0.location != nil && !$0.isInServiceArea }
        withoutFix = drivers.filter { $0.location == nil }
    }

    /// Not on the first view of the map, for the notice that points at the list.
    var offMapCount: Int { faraway.count + withoutFix.count }
}

/// The legend's counts: every car that has sent a location, as the web
/// panel counts them, so its legend and this one read the same numbers.
struct FleetCounts {
    private(set) var byState: [FleetCarState: Int] = [:]
    private(set) var test = 0

    init(_ drivers: [LiveDriver]) {
        for driver in drivers where driver.location != nil {
            byState[driver.carState, default: 0] += 1
            if driver.rehearsing { test += 1 }
        }
    }

    subscript(_ state: FleetCarState) -> Int { byState[state] ?? 0 }
}

enum FleetSearch {
    /// Name, plate or phone, however it was typed: Eastern digits, a plate
    /// without its dash, a phone without its +93.
    static func matches(_ driver: LiveDriver, query: String) -> Bool {
        let text = Numerals.latin(query).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return true }
        if let name = driver.name, name.range(of: text, options: [.caseInsensitive, .diacriticInsensitive]) != nil {
            return true
        }
        let compact = squeeze(text)
        guard !compact.isEmpty else { return false }
        if let plate = driver.vehicle?.plate, squeeze(plate).contains(compact) { return true }
        let digits = text.filter(\.isNumber)
        if digits.count >= 3, let phone = driver.phone, phone.filter(\.isNumber).contains(digits) { return true }
        return false
    }

    private static func squeeze(_ text: String) -> String {
        String(text.lowercased().filter { $0.isLetter || $0.isNumber })
    }
}
