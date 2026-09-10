import Foundation
import Observation
import VelroCore

/// The numbers to dial in an emergency, kept on the phone.
///
/// Refreshed whenever there happens to be a connection and read from disk the
/// rest of the time. Never fetched at the moment somebody needs a number:
/// by then it is too late to ask. Until the first refresh lands, the national
/// numbers are known anyway.
@MainActor
@Observable
final class SafetyContactsStore {
    private(set) var contacts: SafetyContacts
    private let cache: ResponseCache
    private static let key = "support-contacts"

    /// Afghan police and ambulance, as the Android app and the backend's
    /// default settings have them. Compiled in: the moment these are needed
    /// is the moment the network is least likely to be there.
    static let builtIn = SafetyContacts(
        emergencyNumbers: ["119", "100"],
        velroNumber: nil,
        categories: ["SAFETY", "DRIVER_CONDUCT", "PASSENGER_CONDUCT", "APP_PROBLEM",
                     "FARE_DISPUTE", "LOST_ITEM", "VEHICLE_CONDITION", "OTHER"],
        urgentCategories: ["SAFETY", "DRIVER_CONDUCT", "PASSENGER_CONDUCT"]
    )

    init(cache: ResponseCache) {
        self.cache = cache
        contacts = cache.value(SafetyContacts.self, key: Self.key) ?? Self.builtIn
    }

    func refresh(using client: APIClient) async {
        if let fresh = await client.send(API.safetyContacts(), caching: Self.key, in: cache).value {
            contacts = fresh
        }
    }
}
