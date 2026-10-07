import Foundation

/// The rules for "where from" that do not need a screen to test (ADR 0015):
/// when a fix may name a spot, what each refusal says, and how the list of
/// recent origins is kept.
public enum Naming {
    /// A fix vaguer than this cannot name a spot -- it could be any of three
    /// villages. Same number as the server's MAX_NAMING_ACCURACY_M, so the app
    /// never offers what the server would refuse.
    public static let maxAccuracyM: Double = 300

    /// Whether the name field is offered for this fix. No accuracy reported is
    /// treated as coarse, not as perfect.
    public static func canName(accuracyM: Double?, inside: Bool) -> Bool {
        guard inside, let accuracyM, accuracyM >= 0 else { return false }
        return accuracyM <= maxAccuracyM
    }

    /// The sentence for the server's refusal reason. Literal keys, one per
    /// reason: the strings test reads source for the keys the apps ask for,
    /// and a key built at runtime would be invisible to it.
    public static func refusalKey(_ reason: String?) -> String {
        switch reason {
        case "personal": "origin.place.refused.personal"
        case "digits", "contact": "origin.place.refused.digits"
        case "generic": "origin.place.refused.generic"
        case "too_long", "empty": "origin.place.refused.too_long"
        case "rejected": "origin.place.refused.rejected"
        case "coarse": "origin.place.need_precise"
        default: "origin.place.refused.personal"
        }
    }
}

/// Somewhere this passenger has asked from before. Kept on the phone only,
/// in the cache that is wiped at sign-out: the server keeps a place's name
/// without its people, and the one list that says "she asked from here"
/// belongs on her own handset.
public struct RecentOrigin: Codable, Sendable, Hashable, Identifiable {
    public let stationId: String
    public let stationName: String
    public let districtId: String
    public let placeId: String?
    public let placeName: String?
    public let usedAt: Date

    public var id: String { stationId + "|" + (placeId ?? "") }

    public init(stationId: String, stationName: String, districtId: String,
                placeId: String? = nil, placeName: String? = nil, usedAt: Date = Date()) {
        self.stationId = stationId
        self.stationName = stationName
        self.districtId = districtId
        self.placeId = placeId
        self.placeName = placeName
        self.usedAt = usedAt
    }

    public static let limit = 5

    /// The list after `entry` is used: newest first, one row per station and
    /// place, never longer than `limit`.
    public static func merged(_ current: [RecentOrigin], with entry: RecentOrigin) -> [RecentOrigin] {
        Array(([entry] + current.filter { $0.id != entry.id }).prefix(limit))
    }
}
