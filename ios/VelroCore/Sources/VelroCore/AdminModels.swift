import Foundation

// The wire shapes the operations app (VELRO Ops) reads: the admin panel's
// endpoints, decoded from the API's snake_case exactly as the panel's
// TypeScript interfaces declare them (admin/src/pages/*.tsx), with the
// backend routers as the source of truth.
//
// Conventions, the same as the passenger's and the driver's models:
//   * Money is integer minor units: `Money` where the server nests
//     {amount_minor, currency}, `Int64` beside a currency where it sends them
//     flat -- each flat one has a `Money` accessor.
//   * Timestamps stay the server's ISO text and are read with `ISODate`, so
//     an odd one is nil on screen rather than a failed list.
//   * Statuses use the lenient enums the apps already share: a status the
//     server adds tomorrow decodes to a fallback rather than failing a list.
//   * Anything the server may omit or send as null is optional.
//
// Driver and vehicle papers use `DocumentChecklist` and `VehicleChecklist`
// from DriverModels.swift: the admin endpoints answer with the same shape.

// MARK: - Who may do what

/// The six staff roles, as the server names them.
public enum StaffRole: String, CaseIterable, Sendable {
    case superAdmin = "SUPER_ADMIN"
    case admin = "ADMIN"
    case operationsManager = "OPERATIONS_MANAGER"
    case dispatcher = "DISPATCHER"
    case financeManager = "FINANCE_MANAGER"
    case supportAgent = "SUPPORT_AGENT"

    /// "role.super_admin" -- every role has a name in the locale files.
    public var messageKey: String { "role." + rawValue.lowercased() }
}

/// What a set of roles opens, by the server's own dependencies
/// (backend/ui/api/deps.py): `require_staff`, `require_operations`,
/// `require_finance`, `require_support`, `require_admin`.
///
/// A screen hides what a role cannot use; the server refuses it regardless.
/// The same rule as admin/src/api/roles.ts for who may sign in at all.
public struct StaffAccess: Sendable, Hashable {
    public let roles: Set<String>

    public init(roles: some Sequence<String>) { self.roles = Set(roles) }

    public static let staffRoles: Set<String> = Set(StaffRole.allCases.map(\.rawValue))
    public static let operationsRoles: Set<String> = [
        StaffRole.superAdmin.rawValue, StaffRole.admin.rawValue,
        StaffRole.operationsManager.rawValue, StaffRole.dispatcher.rawValue,
    ]
    public static let financeRoles: Set<String> = [
        StaffRole.superAdmin.rawValue, StaffRole.admin.rawValue, StaffRole.financeManager.rawValue,
    ]
    /// Narrower than staff on purpose: a support request may describe an
    /// assault, and a dispatcher or a finance manager has no reason to read it.
    public static let supportRoles: Set<String> = [
        StaffRole.superAdmin.rawValue, StaffRole.admin.rawValue, StaffRole.supportAgent.rawValue,
    ]
    public static let adminRoles: Set<String> = [StaffRole.superAdmin.rawValue, StaffRole.admin.rawValue]

    /// May use the console at all. A passenger's or a driver's session is
    /// valid and has no business here.
    public var isStaff: Bool { !roles.isDisjoint(with: Self.staffRoles) }
    /// Dispatch, the live map, approvals, users, live requests.
    public var isOperations: Bool { !roles.isDisjoint(with: Self.operationsRoles) }
    /// Payouts, debtors, the finance summary, prices.
    public var isFinance: Bool { !roles.isDisjoint(with: Self.financeRoles) }
    /// The support queue.
    public var isSupport: Bool { !roles.isDisjoint(with: Self.supportRoles) }
    /// The audit log and the server's settings.
    public var isAdmin: Bool { !roles.isDisjoint(with: Self.adminRoles) }

    /// The staff roles held, in the server's order, for an account screen.
    public var staffRoles: [StaffRole] { StaffRole.allCases.filter { roles.contains($0.rawValue) } }

    public static func isStaff(_ roles: [String]) -> Bool { StaffAccess(roles: roles).isStaff }
}

// MARK: - Statuses only the office sees

public enum UserStatus: String, LenientStatus, CaseIterable {
    case active = "ACTIVE", suspended = "SUSPENDED", deactivated = "DEACTIVATED"
    public static let fallback = UserStatus.active

    public var tone: StatusTone {
        switch self {
        case .active: .active
        case .suspended: .failed
        case .deactivated: .ended
        }
    }
}

/// Which way a settlement moves money. With cash fares the usual one is
/// COLLECTION: the driver handing VELRO its share.
public enum SettlementDirection: String, LenientStatus {
    case payout = "PAYOUT", collection = "COLLECTION"
    public static let fallback = SettlementDirection.collection
}

extension SettlementStatus {
    public var messageKey: String { "settlement.status." + rawValue.lowercased() }

    public var tone: StatusTone {
        switch self {
        case .pending: .attention
        case .processing: .active
        case .paid: .ended
        case .rejected: .failed
        }
    }
}

extension DocumentStatus {
    public var messageKey: String { "document.status." + rawValue.lowercased() }

    public var tone: StatusTone {
        switch self {
        case .pending: .attention
        case .verified: .active
        case .rejected, .expired: .failed
        }
    }
}

extension TicketStatus {
    public var messageKey: String { "ticket.status." + rawValue.lowercased() }

    public var tone: StatusTone {
        switch self {
        case .open: .attention
        case .inProgress: .active
        case .resolved, .closed: .ended
        }
    }
}

extension DriverApprovalStatus {
    public var messageKey: String { "driver.approval." + rawValue.lowercased() }

    /// The admin panel's DRIVER_TONES.
    public var tone: StatusTone {
        switch self {
        case .approved: .active
        case .pending: .attention
        case .rejected, .suspended: .failed
        }
    }
}

extension VehicleStatus {
    public var messageKey: String { "vehicle.status." + rawValue.lowercased() }

    public var tone: StatusTone {
        switch self {
        case .active: .active
        case .pending: .attention
        case .suspended: .failed
        case .retired: .ended
        }
    }
}

// MARK: - The dashboard, section 47

/// `GET admin/dashboard`: what is happening now, what needs somebody, what
/// is about to go wrong, and how today went (backend/ui/api/opscentre.py).
///
/// Every "act" number has a filtered list behind it -- `Attention` says
/// which in its comments -- and the list filters by the same clause the
/// number counts with, so a card and its rows cannot disagree.
public struct DashboardSnapshot: Decodable, Sendable, Hashable {
    public let generatedAt: String?
    public let live: Live
    public let attention: Attention
    public let today: Today
    public let capacity: Capacity
    public let drivers: Drivers
    public let finance: Finance
    public let network: Network
    public let people: People
    /// Optional, as in the panel: a client a minute ahead of its server
    /// still opens, with this section missing rather than the page broken.
    public let history: WeekHistory?
    public let apps: AppsReport?

    public var generated: Date? { ISODate.parse(generatedAt) }

    public struct Live: Decodable, Sendable, Hashable {
        /// DRIVER_ASSIGNED, DRIVER_ARRIVING. List: `TripFilter(activeOnly: true)`.
        public let onTheWay: Int
        /// ARRIVED_AT_PICKUP, BOARDING.
        public let atTheStation: Int
        /// IN_TRANSIT, ARRIVED.
        public let moving: Int
        /// Leaving within two hours. List: `TripFilter(departingWithinHours: 2)`.
        public let departingSoon: Int
    }

    public struct Attention: Decodable, Sendable, Hashable {
        /// List: `AdminAPI.unassigned()` (or `TripFilter(unassigned: true)`).
        public let unassignedTrips: Int
        /// Leaving within the at-risk window with no driver. List: the dispatch board's `atRisk` rows.
        public let departuresAtRisk: Int
        /// List: `TripFilter(overdue: true)`.
        public let overdueTrips: Int
        /// List: `AdminAPI.rideRequests()`.
        public let openRequests: Int
        /// Open requests no driver has answered. List: `rideRequests()` rows with `offerCount == 0`.
        public let unansweredRequests: Int
        /// List: `AdminAPI.drivers(approvalStatus: .pending)`.
        public let pendingDrivers: Int
        /// List: `AdminAPI.pendingVehicles()`.
        public let pendingVehicles: Int
        /// Driver and vehicle papers awaiting review. No list endpoint of its own.
        public let pendingDocuments: Int
        /// Verified papers running out within 30 days. No list endpoint of its own.
        public let expiringDocuments: Int
        /// OPEN and IN_PROGRESS. List: `AdminAPI.supportTickets()`.
        public let openTickets: Int
        /// Working drivers with no recent fix. List: `AdminAPI.drivers(staleGPS: true)`.
        public let staleGpsDrivers: Int

        /// Everything above that asks somebody to act, summed. Zero is
        /// "nothing needs you right now".
        public var total: Int {
            unassignedTrips + overdueTrips + unansweredRequests + pendingDrivers + pendingVehicles
                + pendingDocuments + openTickets + staleGpsDrivers
        }
    }

    public struct Today: Decodable, Sendable, Hashable {
        public let trips: Int
        public let bookings: Int
        public let completedTrips: Int
        public let cancellations: Int
        public let seatsCapacity: Int
        public let seatsSold: Int
        /// Null when nothing was on offer today, which is not 0%.
        public let utilisationPercent: Int?
    }

    public struct Capacity: Decodable, Sendable, Hashable {
        public let upcomingTrips: Int
        public let nearlyFullTrips: Int
        public let emptyDepartures: Int
    }

    public struct Drivers: Decodable, Sendable, Hashable {
        public let online: Int
        public let onTrip: Int
        public let offline: Int
        public let pending: Int
        public let suspended: Int
        public let total: Int
        public let withoutFix: Int
    }

    public struct Finance: Decodable, Sendable, Hashable {
        public let currency: String
        public let revenueTodayMinor: Int64
        public let commissionTodayMinor: Int64
        public let driverEarningsTodayMinor: Int64
        /// Cash fares: drivers hold VELRO's share until they hand it in.
        public let cashOwedMinor: Int64
        public let payoutsDueMinor: Int64
        public let settlementsOpen: Int

        public var revenueToday: Money { Money(amountMinor: revenueTodayMinor, currency: currency) }
        public var commissionToday: Money { Money(amountMinor: commissionTodayMinor, currency: currency) }
        public var driverEarningsToday: Money { Money(amountMinor: driverEarningsTodayMinor, currency: currency) }
        public var cashOwed: Money { Money(amountMinor: cashOwedMinor, currency: currency) }
        public var payoutsDue: Money { Money(amountMinor: payoutsDueMinor, currency: currency) }
    }

    public struct Network: Decodable, Sendable, Hashable {
        public let routesActive: Int
        public let stations: Int
        public let villages: Int
        public let villagesWithoutCoordinates: Int
        public let villagesWithoutStations: Int
        public let stationsWithoutRoutes: Int
        public let routesWithoutUpcomingTrips: Int
    }

    public struct People: Decodable, Sendable, Hashable {
        public let passengers: Int
        public let drivers: Int
    }
}

/// The last seven Kabul business days, oldest first, today last. A day
/// nothing happened on is there, as zeros.
public struct WeekHistory: Decodable, Sendable, Hashable {
    public let currency: String
    public let days: [HistoryDay]
}

public struct HistoryDay: Decodable, Sendable, Hashable, Identifiable {
    /// A Kabul calendar day, YYYY-MM-DD.
    public let date: String
    public let trips: Int
    public let bookings: Int
    public let completedTrips: Int
    public let cancellations: Int
    public let revenueMinor: Int64
    public let commissionMinor: Int64

    public var id: String { date }
    /// Noon in Kabul on that day, so no time zone can move it.
    public var day: Date? { ISODate.parseDay(date) }
}

/// What is published beside what is actually launching.
public struct AppsReport: Decodable, Sendable, Hashable {
    public let windowDays: Int
    public let latest: Latest?
    public let versions: [AppVersionCount]

    public struct Latest: Decodable, Sendable, Hashable {
        public let passenger: AppVersion?
        public let driver: AppVersion?
    }
}

public struct AppVersion: Decodable, Sendable, Hashable {
    public let versionCode: Int
    public let versionName: String
}

public struct AppVersionCount: Decodable, Sendable, Hashable, Identifiable {
    /// "passenger" or "driver".
    public let app: String
    /// "android" or "ios".
    public let platform: String
    public let versionCode: Int
    public let versionName: String
    public let checks: Int

    public var id: String { "\(app):\(platform):\(versionCode)" }
}

// MARK: - The live map

/// `GET admin/live-map`: every approved driver who is online or on a trip.
public struct LiveMap: Decodable, Sendable, Hashable {
    public let generatedAt: String
    /// The server's threshold. `LiveDriver.Location.stale` is its verdict --
    /// never recomputed on the phone, so a grey pin and the "without a fix"
    /// card agree.
    public let staleAfterSeconds: Int
    public let drivers: [LiveDriver]

    public var generated: Date? { ISODate.parse(generatedAt) }
}

public struct LiveDriver: Decodable, Sendable, Hashable, Identifiable {
    public let driverId: String
    public let name: String?
    public let phone: String?
    /// ONLINE or ON_TRIP.
    public let availability: DriverAvailability
    public let vehicle: Vehicle?
    /// Null when the handset has never sent a position.
    public let location: Location?
    public let trip: Trip?
    /// A test account rehearsing a trip: on the map, never mistaken for service.
    public let rehearsing: Bool

    public var id: String { driverId }
    public var isOnTrip: Bool { availability == .onTrip }

    public struct Vehicle: Decodable, Sendable, Hashable {
        public let plate: String
        public let brand: String?
        public let model: String?

        /// "Toyota Corolla", or nil when neither was given.
        public var makeAndModel: String? {
            let words = [brand, model].compactMap { $0?.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
            return words.isEmpty ? nil : words.joined(separator: " ")
        }
    }

    public struct Location: Decodable, Sendable, Hashable {
        public let latitude: Double
        public let longitude: Double
        public let headingDegrees: Double?
        public let recordedAt: String
        public let stale: Bool

        public var recorded: Date? { ISODate.parse(recordedAt) }
    }

    public struct Trip: Decodable, Sendable, Hashable, Identifiable {
        public let id: String
        /// Always text here; the panel's type allows a number, so one is read as its digits.
        public let number: String
        public let status: TripStatus
        public let originName: String?
        public let destinationName: String?

        private enum CodingKeys: String, CodingKey { case id, number, status, originName, destinationName }

        public init(from decoder: any Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            id = try container.decode(String.self, forKey: .id)
            if let text = try? container.decode(String.self, forKey: .number) {
                number = text
            } else {
                number = String(try container.decode(Int64.self, forKey: .number))
            }
            status = try container.decode(TripStatus.self, forKey: .status)
            originName = try container.decodeIfPresent(String.self, forKey: .originName)
            destinationName = try container.decodeIfPresent(String.self, forKey: .destinationName)
        }
    }
}

// MARK: - Drivers, vehicles, papers

/// A row of `GET admin/drivers`.
public struct AdminDriver: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let userId: String
    public let fullName: String?
    /// Null once the driver deleted his own account.
    public let phone: String?
    public let approvalStatus: DriverApprovalStatus
    public let availability: DriverAvailability
    public let ratingAverage: Double?
    public let ratingCount: Int
    public let completedTrips: Int
    /// The active car if there is one, else the most recently registered.
    public let plateNumber: String?
    public let vehicleStatus: VehicleStatus?
    /// Seconds since the handset last sent a position; null when it never has.
    public let locationAgeSeconds: Int?

    public var isWorking: Bool { availability == .online || availability == .onTrip }
}

/// A row of `GET admin/vehicles`.
public struct AdminVehicle: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let driverId: String
    public let driverName: String?
    public let driverPhone: String?
    public let vehicleTypeCode: String
    public let plateNumber: String
    public let seatCapacity: Int
    public let brand: String?
    public let model: String?
    public let colour: String?
    public let status: VehicleStatus
}

/// A row of `GET admin/vehicles/pending`: a car waiting to be activated,
/// with the driver it belongs to.
public struct PendingVehicle: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let vehicleTypeCode: String
    public let plateNumber: String
    public let seatCapacity: Int
    public let brand: String?
    public let model: String?
    public let year: Int?
    public let colour: String?
    public let status: VehicleStatus
    public let driverId: String
    public let driverName: String?
    public let driverPhone: String?
    public let driverApprovalStatus: DriverApprovalStatus
}

/// `POST admin/drivers/{id}/approve` and `/suspend`.
public struct DriverDecision: Decodable, Sendable, Hashable {
    public let driverId: String
    public let approvalStatus: DriverApprovalStatus
}

/// `POST admin/vehicles/{id}/decide`.
public struct VehicleDecision: Decodable, Sendable, Hashable {
    public let vehicleId: String
    public let status: VehicleStatus
}

/// `POST admin/documents/{id}/review`.
public struct DocumentReview: Decodable, Sendable, Hashable {
    public let documentId: String
    public let driverId: String
    public let status: DocumentStatus
    /// Every required paper is now verified: the driver can be approved.
    public let driverNowComplete: Bool
    public let missingDocuments: [String]
}

/// `POST admin/vehicle-documents/{id}/review`.
public struct VehicleDocumentReview: Decodable, Sendable, Hashable {
    public let documentId: String
    public let vehicleId: String
    public let status: DocumentStatus
    public let vehicleNowComplete: Bool
    public let missingDocuments: [String]
}

// MARK: - Trips, bookings, dispatch

/// A row of `GET admin/trips`, the live board (section 53).
public struct AdminTrip: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let number: String
    public let status: TripStatus
    /// SHARED or PRIVATE.
    public let rideKind: String
    public let scheduledDepartureAt: String
    public let originStationName: String
    public let destinationName: String
    public let driverName: String?
    public let driverPhone: String?
    public let plateNumber: String?
    public let seatCapacity: Int
    public let seatsAvailable: Int
    public let bookedSeats: Int

    public var departure: Date? { ISODate.parse(scheduledDepartureAt) }
    public var hasDriver: Bool { driverName != nil || plateNumber != nil }
}

/// A row of `GET admin/bookings`. The boarding code is deliberately absent:
/// staff have no reason to see it.
public struct AdminBooking: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let number: String
    public let tripNumber: String
    /// The trip it belongs to. Optional: a server before this field sends none.
    public let tripId: String?
    public let passengerName: String?
    public let passengerPhone: String?
    public let status: BookingStatus
    public let seatCount: Int
    public let fareTotalMinor: Int64
    public let fareCurrency: String
    /// CASH, MOBILE_WALLET, CARD, CORPORATE: "payment.method.<lowercased>".
    public let paymentMethod: String
    /// PENDING, COLLECTED, FAILED, REFUNDED: "payment.status.<lowercased>".
    public let paymentStatus: String?
    public let createdAt: String

    public var fare: Money { Money(amountMinor: fareTotalMinor, currency: fareCurrency) }
    public var created: Date? { ISODate.parse(createdAt) }
}

/// A row of `GET dispatch/unassigned`: a trip that needs a driver, and what
/// can be done about it. The board's totals are in the envelope's meta --
/// read it with `APIClient.sendWithMeta` (`count`, `atRisk`, `driversAvailable`).
public struct UnassignedTrip: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let number: String
    public let status: TripStatus
    public let rideKind: String
    public let scheduledDepartureAt: String
    /// Negative once the departure has passed.
    public let minutesToDeparture: Int
    /// Leaving within the at-risk window with nobody to drive it.
    public let atRisk: Bool
    public let originStationId: String
    public let originStationName: String?
    public let destinationId: String
    public let destinationName: String?
    public let seatCapacity: Int
    public let seatsAvailable: Int
    public let bookedSeats: Int
    /// Offers still on drivers' screens.
    public let openOffers: Int
    public let offersExpireAt: String?
    /// From the server's clock, so the phone never compares its own.
    public let offersExpireInMinutes: Int?
    /// Drivers online now with an active car big enough. Zero means offering
    /// would achieve nothing.
    public let candidates: Int

    public var departure: Date? { ISODate.parse(scheduledDepartureAt) }
    public var isPastDeparture: Bool { minutesToDeparture < 0 }
}

/// `POST dispatch/trips/{id}/offer`.
public struct OfferTripResult: Decodable, Sendable, Hashable {
    public let tripId: String
    /// Zero when every driver who could take it already has the offer.
    public let offersMade: Int
    public let driverIds: [String]
}

/// A row of `GET admin/ride-requests`: a passenger waiting, and what drivers
/// have offered. Read-only: the fare is between the passenger and the driver.
public struct AdminRideRequest: Decodable, Sendable, Hashable, Identifiable {
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
    public let requestedFor: String
    public let returnFor: String?
    public let expiresAt: String
    public let createdAt: String
    public let tripId: String?
    public let bookingId: String?
    public let offers: [Offer]
    public let passengerName: String?
    public let passengerPhone: String?
    /// Has anyone answered this person at all.
    public let offerCount: Int

    public var created: Date? { ISODate.parse(createdAt) }
    public var travelsAt: Date? { ISODate.parse(requestedFor) }
    public var expires: Date? { ISODate.parse(expiresAt) }
    public var isUnanswered: Bool { offerCount == 0 }

    public struct Offer: Decodable, Sendable, Hashable, Identifiable {
        public let id: String
        public let rideRequestId: String?
        public let driverId: String?
        public let amount: Money
        public let returnAmount: Money?
        /// OFFERED, ACCEPTED, WITHDRAWN, REJECTED, EXPIRED.
        public let status: String?
        public let note: String?
        public let createdAt: String?
        public let driverName: String?
        public let driverRating: Double?
        public let driverTrips: Int?
        public let vehiclePlate: String?
        public let vehicleDescription: String?
    }
}

// MARK: - Money

/// A row of `GET admin/settlements` (the open queue), and what
/// `decide` and `collect` answer with.
public struct AdminSettlement: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let reference: String
    public let amount: Money
    public let direction: SettlementDirection
    public let status: SettlementStatus
    /// Calendar days, YYYY-MM-DD.
    public let periodStart: String?
    public let periodEnd: String?
    public let paidAt: String?
    public let rejectionReason: String?
    public let driverId: String
    public let driverName: String?
    public let driverPhone: String?

    public var paid: Date? { ISODate.parse(paidAt) }
    /// The next steps the server's settlement lifecycle allows from here.
    public var nextSteps: [SettlementStatus] {
        switch status {
        // The server's SETTLEMENT_LIFECYCLE: money is sent before it is paid.
        case .pending: [.processing, .rejected]
        case .processing: [.paid, .rejected]
        case .paid, .rejected: []
        }
    }
}

/// A row of `GET admin/settlements/debtors`: who is holding VELRO's money.
/// With cash fares this is the ordinary state of an active driver.
public struct Debtor: Decodable, Sendable, Hashable, Identifiable {
    public let driverId: String
    public let driverName: String?
    public let driverPhone: String?
    public let amountOwed: Money
    public let completedTrips: Int

    public var id: String { driverId }
}

/// `GET admin/finance?days=N`. Every figure is the stored split, never
/// recomputed from a rate that may have changed since.
public struct FinanceSummary: Decodable, Sendable, Hashable {
    /// Calendar days, YYYY-MM-DD.
    public let periodStart: String
    public let periodEnd: String
    public let grossMinor: Int64
    public let platformMinor: Int64
    public let driverMinor: Int64
    public let currency: String
    public let completedBookings: Int
    public let cashMinor: Int64
    public let onlineMinor: Int64
    /// What drivers are owed and not yet paid: the sum of wallets, so it goes
    /// negative when drivers owe VELRO more than it owes them.
    public let pendingSettlementMinor: Int64
    public let paidSettlementMinor: Int64

    public var gross: Money { money(grossMinor) }
    public var platform: Money { money(platformMinor) }
    public var driver: Money { money(driverMinor) }
    public var cash: Money { money(cashMinor) }
    public var online: Money { money(onlineMinor) }
    public var pendingSettlement: Money { money(pendingSettlementMinor) }
    public var paidSettlement: Money { money(paidSettlementMinor) }

    private func money(_ minor: Int64) -> Money { Money(amountMinor: minor, currency: currency) }
}

// MARK: - Support

/// `GET admin/support/tickets`: urgent first, then oldest -- the order is the triage.
public struct SupportQueue: Decodable, Sendable, Hashable {
    public let tickets: [AdminTicket]
    /// Across the whole queue, whatever the filter.
    public let open: Int
    public let urgentOpen: Int
}

/// A support request as staff see it, internal notes included.
public struct AdminTicket: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let reference: String
    /// "ticket.category.<lowercased>".
    public let categoryCode: String
    public let subject: String
    public let status: TicketStatus
    public let isUrgent: Bool
    public let tripId: String?
    public let bookingId: String?
    public let createdAt: String
    public let resolvedAt: String?
    public let messages: [AdminTicketMessage]

    public var created: Date? { ISODate.parse(createdAt) }
    public var categoryKey: String { "ticket.category." + categoryCode.lowercased() }
    public var canReply: Bool { status != .closed }
    /// The statuses `decide` accepts from here (IN_PROGRESS, RESOLVED, CLOSED).
    public var nextSteps: [TicketStatus] {
        switch status {
        case .open: [.inProgress, .resolved, .closed]
        case .inProgress: [.resolved, .closed]
        case .resolved: [.inProgress, .closed]
        case .closed: []
        }
    }
}

public struct AdminTicketMessage: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    /// PASSENGER, DRIVER, DISPATCHER, ADMIN, SYSTEM -- a property of the
    /// person, not the message. Use `isFromReporter` to tell who wrote it.
    public let authorRole: String
    public let isFromReporter: Bool?
    public let body: String
    /// Staff-only note; the reporter never sees it.
    public let isInternal: Bool
    public let sentAt: String

    public var sent: Date? { ISODate.parse(sentAt) }
}

/// `POST admin/support/tickets/{id}/decide` and `POST support/tickets/{id}/messages`.
public struct TicketUpdate: Decodable, Sendable, Hashable {
    public let ticketId: String
    public let status: TicketStatus
}

// MARK: - People and the record

/// A row of `GET admin/users`.
public struct AdminUser: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    /// Null on an account its owner deleted (DEACTIVATED).
    public let phone: String?
    public let fullName: String?
    public let status: UserStatus
    public let locale: String
    public let roles: [String]
    public let ratingAverage: Double?
    public let ratingCount: Int
    public let createdAt: String?
    public let lastSeenAt: String?

    public var created: Date? { ISODate.parse(createdAt) }
    public var lastSeen: Date? { ISODate.parse(lastSeenAt) }
    public var isStaff: Bool { StaffAccess.isStaff(roles) }
}

/// `POST admin/users/{id}/suspend` and `/reinstate`.
public struct UserDecision: Decodable, Sendable, Hashable {
    public let userId: String
    public let status: UserStatus
}

/// A row of `GET admin/audit` (section 59): append-only, newest first.
public struct AuditEntry: Decodable, Sendable, Hashable, Identifiable {
    public let id: String
    public let occurredAt: String
    public let actorId: String?
    public let actorName: String?
    /// The collapsed actor role -- ADMIN, DISPATCHER, DRIVER, PASSENGER, SYSTEM.
    public let actorRole: String
    /// "driver.approved", "settings.changed", ...
    public let action: String
    public let entityType: String
    public let entityId: String
    public let before: [String: JSONValue]?
    public let after: [String: JSONValue]?
    /// "api", "script", ...
    public let origin: String

    public var occurred: Date? { ISODate.parse(occurredAt) }
}

// MARK: - Days on the wire

extension ISODate {
    /// A Kabul calendar day as the server reads one, `2026-09-10` -- for an
    /// expiry date picked on a phone in any time zone.
    public static func formatDay(_ date: Date) -> String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = Calendars.kabul
        let parts = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", parts.year ?? 1970, parts.month ?? 1, parts.day ?? 1)
    }
}
