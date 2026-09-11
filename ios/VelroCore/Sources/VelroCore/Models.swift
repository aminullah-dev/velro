import Foundation

// The wire shapes the passenger app reads, decoded straight from the API's
// snake_case. The rules that belong to them -- which offers are still live,
// what a round trip costs, whether a booking can still be cancelled -- live
// here beside them, as they do in the Android app's `:domain`, so a screen
// never works them out for itself.

public struct Money: Codable, Sendable, Hashable {
    public let amountMinor: Int64
    public let currency: String

    public init(amountMinor: Int64, currency: String = "AFN") {
        self.amountMinor = amountMinor
        self.currency = currency
    }

    public static func + (lhs: Money, rhs: Money) -> Money {
        Money(amountMinor: lhs.amountMinor + rhs.amountMinor, currency: lhs.currency)
    }
}

extension MoneyFormatter {
    public static func format(_ money: Money, strings: Strings) -> String {
        format(minor: money.amountMinor, currency: money.currency, strings: strings)
    }
}

/// A status the server may extend: an unknown value decodes to the fallback
/// rather than failing the whole response.
public protocol LenientStatus: RawRepresentable, Decodable, Sendable where RawValue == String {
    static var fallback: Self { get }
}

extension LenientStatus {
    public init(from decoder: any Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = Self(rawValue: raw) ?? .fallback
    }
}

/// How a status reads at a glance. The word is always there too: colour never
/// carries the meaning alone.
public enum StatusTone: Sendable { case neutral, active, attention, ended, failed }

// MARK: - Geography

public struct District: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let code: String
    public let name: String
    public let alternativeName: String?
}

public struct Village: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let code: String
    public let name: String
    public let districtId: String
    public let alternativeNames: [String]?

    /// However the name was typed, under any of its names.
    public func matches(_ query: String) -> Bool {
        ([name] + (alternativeNames ?? [])).contains { PlaceNames.matches($0, query) }
    }
}

public struct Station: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let code: String
    public let name: String
    public let villageId: String
    public let districtId: String
    public let isPrimary: Bool?
    public let description: String?
    public let distanceM: Int?
}

public struct Destination: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let code: String
    public let name: String
    public let kind: String
    public let sortOrder: Int?

    public init(id: String, code: String, name: String, kind: String, sortOrder: Int? = nil) {
        self.id = id
        self.code = code
        self.name = name
        self.kind = kind
        self.sortOrder = sortOrder
    }
}

/// A destination that may open into several: Kabul into Khair Khana, Mina and
/// Jada rather than one vague "Kabul".
public struct DestinationGroup: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let code: String
    public let name: String
    public let kind: String
    public let children: [Destination]

    public var isChoosableItself: Bool { children.isEmpty }
    public var asDestination: Destination { Destination(id: id, code: code, name: name, kind: kind) }
}

public struct GeoSnapshot: Decodable, Sendable {
    public let version: String
    public let districts: [District]
    public let villages: [Village]
    public let stations: [Station]
}

// MARK: - Asking for a ride, section 89

public enum RideRequestStatus: String, LenientStatus {
    case open = "OPEN", matched = "MATCHED", cancelled = "CANCELLED", expired = "EXPIRED"
    public static let fallback = RideRequestStatus.open
}

public enum FareOfferStatus: String, LenientStatus {
    case offered = "OFFERED", accepted = "ACCEPTED", declined = "DECLINED"
    case withdrawn = "WITHDRAWN", expired = "EXPIRED"
    public static let fallback = FareOfferStatus.offered
}

public struct FareOffer: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let rideRequestId: String
    public let driverId: String
    /// The outbound leg, or the whole fare on a one-way journey.
    public let amount: Money
    public let returnAmount: Money?
    public let status: FareOfferStatus
    public let note: String?
    public let driverName: String?
    public let driverRating: Double?
    public let driverTrips: Int?
    public let vehiclePlate: String?
    public let vehicleDescription: String?

    public var isOpen: Bool { status == .offered }

    /// Both legs together. Every comparison is against this, never the
    /// outbound alone: 350 out and 300 back is a 650 journey.
    public var total: Money { returnAmount.map { amount + $0 } ?? amount }

    public func agrees(with asking: Money) -> Bool { total.amountMinor == asking.amountMinor }

    /// How this price differs from what was asked, so nobody subtracts one
    /// number from another at a roadside.
    public func difference(from asking: Money) -> Int64 { total.amountMinor - asking.amountMinor }
}

public struct RideRequest: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let status: RideRequestStatus
    public let originStationId: String
    public let originStationName: String?
    public let destinationId: String
    public let destinationName: String?
    public let passengerCount: Int
    public let offeredFare: Money
    public let returnFare: Money?
    public let agreedFare: Money?
    public let note: String?
    public let requestedFor: String?
    public let returnFor: String?
    public let expiresAt: String?
    /// Set only once matched: a trip, a booking and a boarding code exist.
    /// What tells "your accept worked but the answer was lost" apart from a
    /// request that merely closed.
    public let bookingId: String?
    public let offers: [FareOffer]?
    /// The driver's board only: who is asking, and whether this driver has
    /// already put a price on it.
    public let passengerName: String?
    public let alreadyOffered: Bool?
    public let createdAt: String?

    public var isOpen: Bool { status == .open }

    /// Offers still waiting for an answer, cheapest journey first.
    public var liveOffers: [FareOffer] {
        (offers ?? []).filter(\.isOpen).sorted { $0.total.amountMinor < $1.total.amountMinor }
    }

    /// What was offered for the whole journey -- both legs on a round trip.
    public var askingTotal: Money { returnFare.map { offeredFare + $0 } ?? offeredFare }

    public var expiry: Date? { ISODate.parse(expiresAt) }
    public var departure: Date? { ISODate.parse(requestedFor) }
}

public struct AcceptedOffer: Decodable, Sendable, Equatable {
    public let rideRequestId: String
    public let tripId: String
    public let bookingId: String
    public let bookingNumber: String
    public let verificationCode: String
    public let agreedFare: Money
}

// MARK: - Bookings

public enum BookingStatus: String, LenientStatus, CaseIterable {
    case pending = "PENDING", confirmed = "CONFIRMED", driverAssigned = "DRIVER_ASSIGNED"
    case ready = "READY", onboard = "ONBOARD", completed = "COMPLETED"
    case cancelled = "CANCELLED", noShow = "NO_SHOW"
    public static let fallback = BookingStatus.pending

    public var messageKey: String { "booking.status." + rawValue.lowercased() }

    /// The lifecycle's dead ends, as `docs/domain/lifecycles.json` has them.
    public var isTerminal: Bool { self == .completed || self == .cancelled || self == .noShow }

    public var isCancellable: Bool { [.pending, .confirmed, .driverAssigned, .ready].contains(self) }

    public var tone: StatusTone {
        switch self {
        case .pending: .neutral
        case .confirmed, .driverAssigned: .active
        case .ready, .onboard: .attention
        case .completed: .ended
        case .cancelled, .noShow: .failed
        }
    }
}

public struct FareComponent: Decodable, Sendable, Hashable {
    /// A message key, never a sentence.
    public let key: String
    public let amount: Money
    public let quantity: Int?

    public var total: Money { Money(amountMinor: amount.amountMinor * Int64(quantity ?? 1), currency: amount.currency) }
}

public struct Booking: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let number: String
    public let tripId: String
    public let status: BookingStatus
    public let seatCount: Int
    public let seatNumbers: [Int]
    public let pickupStationId: String
    public let dropoffDestinationId: String
    public let pickupStationName: String?
    public let dropoffDestinationName: String?
    public let fareTotal: Money
    public let fareBreakdown: [FareComponent]?
    public let paymentMethod: String
    public let scheduledDepartureAt: String?
    public let driverName: String?
    /// Present only while the journey is still ahead.
    public let driverPhone: String?
    public let vehiclePlate: String?
    public let vehicleDescription: String?
    public let cancellationReasonCode: String?
    public let cancellationFee: Money?
    /// Only for the passenger who owns it: it is what boards them.
    public let verificationCode: String?
    public let createdAt: String?

    public var isActive: Bool { !status.isTerminal }
    public var canCancel: Bool { status.isCancellable }
    public var canRate: Bool { status == .completed }
    public var departure: Date? { ISODate.parse(scheduledDepartureAt) }
    public var created: Date? { ISODate.parse(createdAt) }

    /// A receipt whose lines do not add up is worse than one with none.
    public var breakdownExplainsTotal: Bool {
        guard let lines = fareBreakdown, !lines.isEmpty else { return false }
        return lines.reduce(0) { $0 + $1.total.amountMinor } == fareTotal.amountMinor
    }
}

public struct BookingPage: Decodable, Sendable {
    public let bookings: [Booking]
    public let hasMore: Bool?
    public let nextOffset: Int?
}

public struct CancelledBooking: Decodable, Sendable {
    public let bookingId: String
    public let status: BookingStatus
    public let seatsReleased: Int
    public let fee: Money
}

public struct RideVehicle: Decodable, Sendable, Hashable {
    public let brand: String?
    public let model: String?
    public let colour: String?
    public let plateNumber: String
    public let seatCapacity: Int
}

/// The driver of a booked journey: shown to the passenger who is about to get
/// into his car.
public struct RideDriver: Decodable, Sendable, Hashable {
    public let driverId: String
    public let name: String?
    public let phone: String
    public let ratingAverage: Double?
    public let ratingCount: Int?
    public let vehicle: RideVehicle?
}

public struct VehicleLocation: Decodable, Sendable, Hashable {
    public let latitude: Double
    public let longitude: Double
    public let headingDegrees: Int?
    public let recordedAt: String
    public let ageSeconds: Int
}

// MARK: - Safety

public struct SafetyContacts: Codable, Sendable, Hashable {
    public let emergencyNumbers: [String]
    public let velroNumber: String?
    public let categories: [String]
    public let urgentCategories: [String]

    public init(emergencyNumbers: [String], velroNumber: String?, categories: [String], urgentCategories: [String]) {
        self.emergencyNumbers = emergencyNumbers
        self.velroNumber = velroNumber
        self.categories = categories
        self.urgentCategories = urgentCategories
    }
}

public enum TicketStatus: String, LenientStatus {
    case open = "OPEN", inProgress = "IN_PROGRESS", resolved = "RESOLVED", closed = "CLOSED"
    public static let fallback = TicketStatus.open
}

public struct TicketMessage: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let isFromReporter: Bool?
    public let body: String
    public let sentAt: String
}

public struct Ticket: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let reference: String
    public let categoryCode: String
    public let status: TicketStatus
    public let isUrgent: Bool?
    public let createdAt: String
    public let messages: [TicketMessage]?

    public var canReply: Bool { status != .closed }
    public var hasAnswer: Bool { (messages ?? []).contains { $0.isFromReporter == false } }
}

public struct RaisedTicket: Decodable, Sendable, Hashable {
    public let id: String
    public let reference: String
    public let status: TicketStatus
    public let isUrgent: Bool?
}
