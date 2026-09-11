import Foundation

// The wire shapes the driver app reads, and the rules that belong to them:
// which step comes next on a trip, whether it can still be called off, who in
// the car has had their code checked, whether the driver may work at all.
// They are the Android app's `DriverHomeUiState` and `Lifecycles.trip`,
// moved beside the data as the passenger's rules are in Models.swift, so no
// screen works them out for itself and the two apps cannot disagree.

// MARK: - The driver

public enum DriverAvailability: String, LenientStatus {
    case offline = "OFFLINE", online = "ONLINE", busy = "BUSY", onTrip = "ON_TRIP"
    public static let fallback = DriverAvailability.offline
}

public enum DriverApprovalStatus: String, LenientStatus {
    case pending = "PENDING", approved = "APPROVED", rejected = "REJECTED", suspended = "SUSPENDED"
    public static let fallback = DriverApprovalStatus.pending
}

public enum VehicleStatus: String, LenientStatus {
    case pending = "PENDING", active = "ACTIVE", suspended = "SUSPENDED", retired = "RETIRED"
    public static let fallback = VehicleStatus.pending
}

public struct DriverVehicle: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let vehicleTypeCode: String
    public let plateNumber: String
    public let seatCapacity: Int
    public let brand: String?
    public let model: String?
    public let year: Int?
    public let colour: String?
    public let status: VehicleStatus

    /// Only an active car may carry anyone; the server refuses the rest.
    public var isReadyForWork: Bool { status == .active }

    /// "Toyota Corolla", or nil when neither was given.
    public var makeAndModel: String? {
        let words = [brand, model].compactMap { $0?.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
        return words.isEmpty ? nil : words.joined(separator: " ")
    }
}

public struct VehicleType: Decodable, Sendable, Hashable, Identifiable {
    public let code: String
    public let nameKey: String
    public let defaultSeatCapacity: Int
    public var id: String { code }
}

public struct DriverProfile: Decodable, Sendable, Hashable {
    public let id: String
    public let userId: String
    public let fullName: String?
    public let approvalStatus: DriverApprovalStatus
    public let availability: DriverAvailability
    public let ratingAverage: Double?
    public let ratingCount: Int?
    public let completedTrips: Int?
    public let vehicle: DriverVehicle?
    public let missingDocuments: [String]?

    /// The single gate before any work is shown. Mirrors the server's rule so
    /// the app can say why; the server still refuses independently.
    public var canWork: Bool {
        approvalStatus == .approved && (missingDocuments ?? []).isEmpty && vehicle?.isReadyForWork == true
    }

    /// Which half of the gate is shut: the car, or the person. They are fixed
    /// on different screens, so "not approved" alone sends him to the wrong one.
    public var blockedByVehicle: Bool { !canWork && vehicle?.isReadyForWork != true }

    public var isOnline: Bool { availability == .online || availability == .onTrip }
}

// MARK: - Trips

public enum TripStatus: String, LenientStatus, CaseIterable {
    case scheduled = "SCHEDULED", requested = "REQUESTED"
    case driverAssigned = "DRIVER_ASSIGNED", driverArriving = "DRIVER_ARRIVING"
    case arrivedAtPickup = "ARRIVED_AT_PICKUP", boarding = "BOARDING"
    case inTransit = "IN_TRANSIT", arrived = "ARRIVED", completed = "COMPLETED"
    case cancelled = "CANCELLED", expired = "EXPIRED", noDriverAvailable = "NO_DRIVER_AVAILABLE"
    public static let fallback = TripStatus.scheduled

    /// The server's transition table, `Lifecycles.trip` on Android.
    static let transitions: [TripStatus: Set<TripStatus>] = [
        .scheduled: [.driverAssigned, .cancelled, .expired],
        .requested: [.driverAssigned, .noDriverAvailable, .cancelled, .expired],
        .driverAssigned: [.driverArriving, .requested, .scheduled, .cancelled],
        .driverArriving: [.arrivedAtPickup, .requested, .cancelled],
        .arrivedAtPickup: [.boarding, .cancelled],
        .boarding: [.inTransit, .cancelled],
        .inTransit: [.arrived],
        .arrived: [.completed],
        .completed: [], .cancelled: [], .expired: [], .noDriverAvailable: [],
    ]

    public func can(_ target: TripStatus) -> Bool { Self.transitions[self]?.contains(target) == true }

    /// The one forward step a driver takes from here, or nil. A button the
    /// server would refuse is never offered.
    public var nextStep: TripStatus? {
        let candidate: TripStatus? = switch self {
        case .driverAssigned: .driverArriving
        case .driverArriving: .arrivedAtPickup
        case .arrivedAtPickup: .boarding
        case .boarding: .inTransit
        case .inTransit: .arrived
        case .arrived: .completed
        default: nil
        }
        guard let candidate, can(candidate) else { return nil }
        return candidate
    }

    /// Once the car is moving with someone in it, the journey finishes or it
    /// is an incident -- not a cancellation.
    public var isCancellable: Bool { can(.cancelled) }

    /// Checking a code only makes sense with the passenger at the car.
    public var acceptsBoardingCodes: Bool { self == .arrivedAtPickup || self == .boarding }

    public var messageKey: String { "trip.status." + rawValue.lowercased() }

    public var tone: StatusTone {
        switch self {
        case .scheduled, .requested: .neutral
        case .driverAssigned, .driverArriving, .inTransit: .active
        case .arrivedAtPickup, .boarding, .arrived: .attention
        case .completed: .ended
        case .cancelled, .expired, .noDriverAvailable: .failed
        }
    }

    /// The button that moves a trip *to* this status names what tapping does,
    /// not the state being left.
    public var actionKey: String {
        switch self {
        case .driverArriving: "driver.action.on_my_way"
        case .arrivedAtPickup: "driver.action.arrived"
        case .boarding: "driver.action.start_boarding"
        case .inTransit: "driver.action.start_trip"
        case .arrived: "driver.action.arrived_destination"
        case .completed: "driver.action.complete_trip"
        default: "common.action.confirm"
        }
    }
}

public struct TripSummary: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let number: String
    public let status: TripStatus
    public let rideKind: String?
    public let scheduledDepartureAt: String?
    public let originStationId: String
    public let originStationName: String?
    public let destinationId: String
    public let destinationName: String?
    public let seatCapacity: Int
    public let seatsAvailable: Int
    public let driverId: String?
    public let vehicleId: String?

    public var departure: Date? { ISODate.parse(scheduledDepartureAt) }
}

public struct ManifestEntry: Decodable, Sendable, Hashable, Identifiable {
    public let bookingId: String
    public let number: String
    public let status: BookingStatus
    public let seatCount: Int
    public let pickupStationId: String?
    public let dropoffDestinationId: String?
    public let passengerName: String?
    public let passengerPhone: String?
    public let fareTotalMinor: Int64?
    public let fareCurrency: String?

    public var id: String { bookingId }

    /// Still somebody expected in the car. A cancelled or no-show row is not.
    public var isRiding: Bool { status != .cancelled && status != .noShow }

    /// The code has been entered: ONBOARD or beyond. A status the app does not
    /// know counts as unchecked -- asking once too often costs a tap, assuming
    /// costs a booked passenger her seat.
    public var isVerified: Bool { status == .onboard || status == .completed }

    public var fare: Money? {
        fareTotalMinor.map { Money(amountMinor: $0, currency: fareCurrency ?? "AFN") }
    }
}

/// The trip that is his right now, and who is on it.
public struct CurrentAssignment: Decodable, Sendable, Hashable {
    public let trip: TripSummary
    public let manifest: [ManifestEntry]?

    public var passengers: [ManifestEntry] { (manifest ?? []).filter(\.isRiding) }
    public var unverified: Int { passengers.filter { !$0.isVerified }.count }

    /// Whether the next tap pulls away with somebody unchecked. A question,
    /// not a wall: a passenger with a dead phone is ordinary on this road.
    public var startsWithUnverified: Bool { trip.status.nextStep == .inTransit && unverified > 0 }

    /// The passenger is aboard and the car is moving: the screen becomes the map.
    public var isRiding: Bool { trip.status == .inTransit }
}

public struct AdvanceOutcome: Decodable, Sendable, Hashable {
    public let tripId: String
    public let status: TripStatus
    public let bookingsAdvanced: Int?
    public let driverEarning: Money?
    public let platformCommission: Money?
}

public struct VerifiedPassenger: Decodable, Sendable, Hashable {
    public let bookingId: String
    public let number: String
    public let passengerName: String?
    public let seatNumbers: [Int]?
    public let status: BookingStatus
}

/// A trip the dispatcher offered him, until it expires or somebody takes it.
public struct DispatchOffer: Decodable, Sendable, Hashable, Identifiable {
    public let offerId: String
    public let expiresAt: String?
    public let trip: TripSummary
    public var id: String { offerId }
    public var expiry: Date? { ISODate.parse(expiresAt) }
}

// MARK: - Money

public struct Earnings: Decodable, Sendable, Hashable {
    /// Signed. Fares are paid in cash at the car, so a driver normally walks
    /// away holding VELRO's share: a negative balance is money he owes.
    public let available: Money
    public let pending: Money
    public let lifetimeEarned: Money
    public let lifetimeCommission: Money
    public let lifetimePaid: Money?
    public let completedTrips: Int

    public var owes: Bool { available.amountMinor < 0 }
    public var owed: Money { Money(amountMinor: abs(available.amountMinor), currency: available.currency) }
}

public struct EarningsBucket: Decodable, Sendable, Hashable, Identifiable {
    public let startsOn: String
    public let earned: Money
    public let commission: Money
    public let net: Money
    public let trips: Int?
    public var id: String { startsOn }
    public var start: Date? { ISODate.parseDay(startsOn) }
}

public struct EarningsSummary: Decodable, Sendable, Hashable {
    public let period: String
    public let buckets: [EarningsBucket]?
}

public struct LedgerEntry: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let kind: String
    public let amount: Money
    public let balanceAfter: Money
    public let createdAt: String
    public let bookingId: String?
    public let tripId: String?
    public let settlementId: String?
    public let note: String?
    public var created: Date? { ISODate.parse(createdAt) }
}

public struct LedgerPage: Decodable, Sendable, Hashable {
    public let entries: [LedgerEntry]?
    public let hasMore: Bool?
    public let nextOffset: Int?
}

public enum SettlementStatus: String, LenientStatus {
    case pending = "PENDING", processing = "PROCESSING", paid = "PAID", rejected = "REJECTED"
    public static let fallback = SettlementStatus.pending
}

public struct Settlement: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let reference: String
    public let amount: Money
    public let direction: String?
    public let status: SettlementStatus
    public let periodStart: String?
    public let periodEnd: String?
    public let paidAt: String?
    public let rejectionReason: String?
}

public struct PayoutOptions: Decodable, Sendable, Hashable {
    public let settlements: [Settlement]?
    public let minimum: Money?
    public let direction: String?
    public let amountOwed: Money?
    public let amountWithdrawable: Money?
    public let canRequest: Bool?
    public let openReference: String?
}

// MARK: - Papers

public enum DocumentStatus: String, LenientStatus {
    case pending = "PENDING", verified = "VERIFIED", rejected = "REJECTED", expired = "EXPIRED"
    public static let fallback = DocumentStatus.pending
}

public struct DriverDocument: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let documentTypeCode: String
    public let status: DocumentStatus
    public let expiresOn: String?
    public let rejectionReason: String?
    public let uploadedAt: String?
    public let reviewedAt: String?
    public let isCurrent: Bool
}

public struct DocumentChecklist: Decodable, Sendable, Hashable {
    public let required: [String]
    public let missing: [String]
    public let documents: [DriverDocument]?
    public let approvalStatus: DriverApprovalStatus
    public let canWork: Bool

    /// The document that stands for this type now: the newest current one.
    public func current(_ type: String) -> DriverDocument? {
        (documents ?? []).first { $0.documentTypeCode == type && $0.isCurrent }
    }
}

public struct VehicleDocument: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let vehicleId: String
    public let documentTypeCode: String
    public let status: DocumentStatus
    public let expiresOn: String?
    public let rejectionReason: String?
    public let uploadedAt: String?
    public let isCurrent: Bool
}

public struct VehicleChecklist: Decodable, Sendable, Hashable {
    public let vehicleId: String
    public let plateNumber: String
    public let required: [String]
    public let missing: [String]
    public let documents: [VehicleDocument]?
    public let vehicleStatus: VehicleStatus
    public let canCarry: Bool

    public func current(_ type: String) -> VehicleDocument? {
        (documents ?? []).first { $0.documentTypeCode == type && $0.isCurrent }
    }
}

public struct UploadedDocument: Decodable, Sendable, Hashable {
    public let id: String
    public let documentTypeCode: String
    public let status: DocumentStatus
}

public struct RegisteredVehicle: Decodable, Sendable, Hashable {
    public let id: String
    public let plateNumber: String
    public let status: VehicleStatus
    public let seatCapacity: Int
}

// MARK: - The inbox

public struct InboxNotification: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let messageKey: String
    /// Whatever the server put there: numbers as well as strings.
    public let payload: [String: JSONValue]?
    public let tripId: String?
    public let bookingId: String?
    public let createdAt: String?
    public let readAt: String?

    public var isUnread: Bool { readAt == nil }

    /// The payload as the arguments its message key interpolates.
    public var arguments: [String: Any] { (payload ?? [:]).arguments }
}

public struct Inbox: Decodable, Sendable, Hashable {
    public let notifications: [InboxNotification]?
    public let unread: Int?
}

// MARK: - What the papers say

extension DocumentChecklist {
    public var isComplete: Bool { missing.isEmpty }
    /// Everything sent, nothing approved yet: the state that needs explaining.
    public var awaitingReview: Bool { isComplete && !canWork }

    public var headlineKey: String {
        canWork ? "driver.documents.approved"
            : awaitingReview ? "driver.documents.awaiting_review"
            : "driver.documents.incomplete"
    }
}

extension VehicleChecklist {
    public var awaitingReview: Bool { missing.isEmpty && !canCarry }
}

/// A paper's expiry, said before it stops him working: a month ahead, and
/// again once it has passed. Android's `expiryNotice`, same thresholds.
public enum DocumentExpiry {
    public enum Severity: Sendable { case fine, soon, past }

    public struct Notice: Equatable, Sendable {
        public let messageKey: String
        public let severity: Severity
        public let date: Date
    }

    public static let warnWithinDays = 30

    public static func notice(expiresOn: String?, today: Date = .now) -> Notice? {
        guard let expiry = ISODate.parseDay(expiresOn) else { return nil }
        var kabul = Calendar(identifier: .gregorian)
        kabul.timeZone = TimeZone(identifier: "Asia/Kabul") ?? .gmt
        let days = kabul.dateComponents([.day], from: kabul.startOfDay(for: today), to: kabul.startOfDay(for: expiry)).day ?? 0
        if days < 0 { return Notice(messageKey: "driver.documents.expired", severity: .past, date: expiry) }
        if days <= warnWithinDays { return Notice(messageKey: "driver.documents.expiring_soon", severity: .soon, date: expiry) }
        return Notice(messageKey: "driver.documents.valid_until", severity: .fine, date: expiry)
    }
}
