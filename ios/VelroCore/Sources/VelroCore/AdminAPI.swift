import Foundation

// Every call VELRO Ops makes, in the shapes the admin panel sends
// (admin/src/pages/*.tsx). The server cannot tell the two consoles apart,
// and must not need to.
//
// Each endpoint's comment names the role dependency the router declares, so
// a screen can hide what the signed-in role cannot use -- see `StaffAccess`.

extension API {
    public static let channelEmail = "email"

    /// A sign-in code for the operations console.
    ///
    /// `audience: "staff"`: the server answers the same way for any number but
    /// only actually sends to one that already holds a staff role, so a
    /// stranger guessing numbers here costs nothing and learns nothing. Email
    /// is honoured only for a staff account with an address on file; the
    /// answer's `channel` says what actually carried it.
    public static func requestStaffOtp(phone: String, locale: AppLocale, channel: String) -> Endpoint<RequestOtpResponse> {
        struct Body: Encodable { let phone: String; let locale: String; let channel: String; let audience: String }
        return .post(
            "auth/otp/request",
            body: Body(phone: phone, locale: locale.tag, channel: channel, audience: "staff"),
            authenticated: false
        )
    }
}

/// Which trips `AdminAPI.trips` lists. The flags are the dashboard's cards,
/// filtered by the same clauses the cards count with.
public struct TripFilter: Sendable, Hashable {
    public var status: TripStatus?
    /// Assigned and not yet finished.
    public var activeOnly: Bool
    /// Needs a driver and is still worth driving.
    public var unassigned: Bool
    /// Time passed, nobody moved it along.
    public var overdue: Bool
    /// 1...72. Sorted soonest first when set.
    public var departingWithinHours: Int?
    /// 1...200.
    public var limit: Int
    public var offset: Int
    /// One trip by its public number, "VLR-2026-000047": exact, though the
    /// server forgives case, spaces and Eastern digits.
    public var number: String?

    public init(
        status: TripStatus? = nil, activeOnly: Bool = false, unassigned: Bool = false,
        overdue: Bool = false, departingWithinHours: Int? = nil, limit: Int = 50, offset: Int = 0,
        number: String? = nil
    ) {
        self.number = number
        self.status = status
        self.activeOnly = activeOnly
        self.unassigned = unassigned
        self.overdue = overdue
        self.departingWithinHours = departingWithinHours
        self.limit = limit
        self.offset = offset
    }

    var queryItems: [URLQueryItem] {
        var items: [URLQueryItem] = []
        if let status { items.append(URLQueryItem(name: "status", value: status.rawValue)) }
        if let number { items.append(URLQueryItem(name: "number", value: number)) }
        if activeOnly { items.append(URLQueryItem(name: "active_only", value: "true")) }
        if unassigned { items.append(URLQueryItem(name: "unassigned", value: "true")) }
        if overdue { items.append(URLQueryItem(name: "overdue", value: "true")) }
        if let departingWithinHours {
            items.append(URLQueryItem(name: "departing_within_hours", value: String(departingWithinHours)))
        }
        items.append(URLQueryItem(name: "limit", value: String(limit)))
        items.append(URLQueryItem(name: "offset", value: String(offset)))
        return items
    }
}

/// Which support requests `AdminAPI.supportTickets` lists.
public enum SupportQueueFilter: Sendable, Hashable {
    /// The server's default: the working queue, OPEN and IN_PROGRESS.
    case working
    /// Every status, closed ones included.
    case all
    case only(TicketStatus)

    var value: String? {
        switch self {
        case .working: nil
        case .all: "ALL"
        case .only(let status): status.rawValue
        }
    }
}

/// The admin panel's endpoints, one function each.
///
/// Reads answer with the models in AdminModels.swift. A list whose total
/// matters (trips, bookings, audit, the dispatch board) is read with
/// `APIClient.sendWithMeta`, which keeps the envelope's meta.
public enum AdminAPI {
    // MARK: The command centre

    /// require_staff.
    public static func dashboard() -> Endpoint<DashboardSnapshot> { .get("admin/dashboard") }

    /// require_operations. Names, phones and live positions together: a
    /// finance manager has no reason to see them.
    public static func liveMap() -> Endpoint<LiveMap> { .get("admin/live-map") }

    // MARK: Drivers

    /// require_staff. `staleGPS`: only working drivers whose last fix is old
    /// or missing -- the dashboard's "without a fix" card.
    /// `search` is matched by the server: a name in any case, a phone in any
    /// form or digits. Paged: `sendWithMeta` for the total.
    public static func drivers(
        approvalStatus: DriverApprovalStatus? = nil, staleGPS: Bool = false, search: String? = nil,
        limit: Int = 100, offset: Int = 0
    ) -> Endpoint<[AdminDriver]> {
        var query: [URLQueryItem] = []
        if let approvalStatus { query.append(URLQueryItem(name: "approval_status", value: approvalStatus.rawValue)) }
        if staleGPS { query.append(URLQueryItem(name: "stale_gps", value: "true")) }
        if let search = clean(search) { query.append(URLQueryItem(name: "search", value: search)) }
        query.append(URLQueryItem(name: "limit", value: String(limit)))
        query.append(URLQueryItem(name: "offset", value: String(offset)))
        return .get("admin/drivers", query: query)
    }

    /// require_operations. Refused while a required paper is unverified
    /// (DRIVER_DOCUMENTS_INCOMPLETE). `fullName` is the name as it reads on
    /// the tazkira, and may replace one already there; nil keeps it.
    public static func approveDriver(_ driverId: String, fullName: String? = nil) -> Endpoint<DriverDecision> {
        struct Body: Encodable { let fullName: String? }
        return .post("admin/drivers/\(driverId)/approve", body: Body(fullName: clean(fullName)))
    }

    /// require_operations. Refused mid-trip (DRIVER_ALREADY_ON_TRIP).
    public static func suspendDriver(_ driverId: String, reason: String?) -> Endpoint<DriverDecision> {
        struct Body: Encodable { let reason: String? }
        return .post("admin/drivers/\(driverId)/suspend", body: Body(reason: clean(reason)))
    }

    /// require_operations. What a driver has sent and where each paper stands.
    public static func driverDocuments(driverId: String) -> Endpoint<DocumentChecklist> {
        .get("admin/drivers/\(driverId)/documents")
    }

    /// require_operations. The bytes of a driver's paper: `APIClient.download`.
    public static func documentFile(_ documentId: String) -> Endpoint<DownloadedFile> {
        .get("admin/documents/\(documentId)/file")
    }

    /// require_operations. A rejection needs a reason the driver will read
    /// (DOCUMENT_REJECTION_REASON_REQUIRED). `expiresOn` is a Kabul day,
    /// YYYY-MM-DD -- `ISODate.formatDay` -- or nil for a paper that does not expire.
    public static func reviewDocument(
        _ documentId: String, verified: Bool, rejectionReason: String? = nil, expiresOn: String? = nil
    ) -> Endpoint<DocumentReview> {
        .post("admin/documents/\(documentId)/review", body: ReviewBody(
            verified: verified, rejectionReason: clean(rejectionReason), expiresOn: expiresOn
        ))
    }

    // MARK: Vehicles

    /// require_staff. Every vehicle, by plate.
    /// `search` matches the plate in any digits, and the owner's name or
    /// phone. Paged: `sendWithMeta` for the total.
    public static func vehicles(search: String? = nil, limit: Int = 100, offset: Int = 0) -> Endpoint<[AdminVehicle]> {
        var query: [URLQueryItem] = []
        if let search = clean(search) { query.append(URLQueryItem(name: "search", value: search)) }
        query.append(URLQueryItem(name: "limit", value: String(limit)))
        query.append(URLQueryItem(name: "offset", value: String(offset)))
        return .get("admin/vehicles", query: query)
    }

    /// require_operations. Cars waiting to be activated, oldest first.
    public static func pendingVehicles(limit: Int = 50) -> Endpoint<[PendingVehicle]> {
        .get("admin/vehicles/pending", query: [URLQueryItem(name: "limit", value: String(limit))])
    }

    /// require_operations. Activate a car, or take one out of service.
    /// Activation is refused while its papers are incomplete.
    public static func decideVehicle(_ vehicleId: String, approve: Bool, reason: String? = nil) -> Endpoint<VehicleDecision> {
        struct Body: Encodable { let approve: Bool; let reason: String? }
        return .post("admin/vehicles/\(vehicleId)/decide", body: Body(approve: approve, reason: clean(reason)))
    }

    /// require_operations. A car's own papers (جواز سیر).
    public static func vehicleDocuments(vehicleId: String) -> Endpoint<VehicleChecklist> {
        .get("admin/vehicles/\(vehicleId)/documents")
    }

    /// require_operations. The bytes of a vehicle's paper: `APIClient.download`.
    public static func vehicleDocumentFile(_ documentId: String) -> Endpoint<DownloadedFile> {
        .get("admin/vehicle-documents/\(documentId)/file")
    }

    /// require_operations. As `reviewDocument`, for a car's paper.
    public static func reviewVehicleDocument(
        _ documentId: String, verified: Bool, rejectionReason: String? = nil, expiresOn: String? = nil
    ) -> Endpoint<VehicleDocumentReview> {
        .post("admin/vehicle-documents/\(documentId)/review", body: ReviewBody(
            verified: verified, rejectionReason: clean(rejectionReason), expiresOn: expiresOn
        ))
    }

    // MARK: Trips, bookings, dispatch

    /// require_staff. The live board, newest departures first (soonest first
    /// when filtering by departure). Paged: `sendWithMeta` for the total.
    public static func trips(_ filter: TripFilter = TripFilter()) -> Endpoint<[AdminTrip]> {
        .get("admin/trips", query: filter.queryItems)
    }

    /// require_staff. Newest first. Paged: `sendWithMeta` for the total.
    public static func bookings(
        status: BookingStatus? = nil, tripId: String? = nil, limit: Int = 50, offset: Int = 0
    ) -> Endpoint<[AdminBooking]> {
        var query: [URLQueryItem] = []
        if let status { query.append(URLQueryItem(name: "status", value: status.rawValue)) }
        if let tripId { query.append(URLQueryItem(name: "trip_id", value: tripId)) }
        query.append(URLQueryItem(name: "limit", value: String(limit)))
        query.append(URLQueryItem(name: "offset", value: String(offset)))
        return .get("admin/bookings", query: query)
    }

    /// require_operations. Trips needing a driver within `withinHours`
    /// (1...72), soonest first. Its meta carries count, at_risk and
    /// drivers_available: `sendWithMeta`.
    public static func unassigned(withinHours: Int = 12) -> Endpoint<[UnassignedTrip]> {
        .get("dispatch/unassigned", query: [URLQueryItem(name: "within_hours", value: String(withinHours))])
    }

    /// require_operations. Offer the trip to every driver who could take it,
    /// ranked by the section 90 ordering. Not keyed: offering again after the
    /// last offers lapsed is a new offer, and one already on a driver's
    /// screen is not duplicated by the server.
    public static func offerTrip(_ tripId: String) -> Endpoint<OfferTripResult> {
        .post("dispatch/trips/\(tripId)/offer")
    }

    /// require_operations. Passengers waiting for offers, and what they have
    /// been offered. Read-only by design.
    public static func rideRequests(limit: Int = 50) -> Endpoint<[AdminRideRequest]> {
        .get("admin/ride-requests", query: [URLQueryItem(name: "limit", value: String(limit))])
    }

    // MARK: Money

    /// require_finance. The open payout queue.
    public static func settlements() -> Endpoint<[AdminSettlement]> { .get("admin/settlements") }

    /// require_finance. Drivers holding VELRO's share of cash fares.
    public static func debtors() -> Endpoint<[Debtor]> { .get("admin/settlements/debtors") }

    /// require_finance. PENDING → PROCESSING → PAID, or REJECTED with a reason
    /// the driver reads. See `AdminSettlement.nextSteps`.
    public static func decideSettlement(_ settlementId: String, to target: SettlementStatus, reason: String? = nil) -> Endpoint<AdminSettlement> {
        struct Body: Encodable { let to: String; let reason: String? }
        return .post("admin/settlements/\(settlementId)/decide", body: Body(to: target.rawValue, reason: clean(reason)))
    }

    /// require_finance. Cash a driver handed in, against what he owes; nil
    /// amount means all of it.
    public static func collect(driverId: String, amountMinor: Int64? = nil) -> Endpoint<AdminSettlement> {
        struct Body: Encodable { let driverId: String; let amountMinor: Int64? }
        return .post("admin/settlements/collect", body: Body(driverId: driverId, amountMinor: amountMinor))
    }

    /// require_finance. The last `days` (1...365), from the stored split.
    public static func finance(days: Int = 30) -> Endpoint<FinanceSummary> {
        .get("admin/finance", query: [URLQueryItem(name: "days", value: String(days))])
    }

    // MARK: Support

    /// require_support. Urgent first, then oldest.
    public static func supportTickets(
        _ filter: SupportQueueFilter = .working, category: String? = nil, limit: Int = 50
    ) -> Endpoint<SupportQueue> {
        var query: [URLQueryItem] = []
        if let status = filter.value { query.append(URLQueryItem(name: "status", value: status)) }
        if let category { query.append(URLQueryItem(name: "category", value: category)) }
        query.append(URLQueryItem(name: "limit", value: String(limit)))
        return .get("admin/support/tickets", query: query)
    }

    /// Any signed-in account; staff see every ticket and its internal notes.
    public static func ticket(_ ticketId: String) -> Endpoint<AdminTicket> {
        .get("support/tickets/\(ticketId)")
    }

    /// A reply, or -- `isInternal` -- a note only staff read. The same
    /// endpoint the reporter writes to; the server honours `isInternal` only
    /// from support staff.
    public static func replyToTicket(_ ticketId: String, body: String, isInternal: Bool = false) -> Endpoint<TicketUpdate> {
        struct Body: Encodable { let body: String; let isInternal: Bool }
        return .post(
            "support/tickets/\(ticketId)/messages",
            body: Body(body: body.trimmingCharacters(in: .whitespacesAndNewlines), isInternal: isInternal)
        )
    }

    /// require_support. IN_PROGRESS, RESOLVED or CLOSED; see `AdminTicket.nextSteps`.
    public static func decideTicket(_ ticketId: String, status: TicketStatus) -> Endpoint<TicketUpdate> {
        struct Body: Encodable { let status: String }
        return .post("admin/support/tickets/\(ticketId)/decide", body: Body(status: status.rawValue))
    }

    // MARK: People

    /// require_operations. `phone` matches on digits, however it is written
    /// (0793…, +93793…).
    public static func users(phone: String? = nil, status: UserStatus? = nil, limit: Int = 50) -> Endpoint<[AdminUser]> {
        var query: [URLQueryItem] = []
        if let phone = clean(phone) { query.append(URLQueryItem(name: "phone", value: Numerals.latin(phone))) }
        if let status { query.append(URLQueryItem(name: "status", value: status.rawValue)) }
        query.append(URLQueryItem(name: "limit", value: String(limit)))
        return .get("admin/users", query: query)
    }

    /// require_operations. The account-level off switch: sign-in and every
    /// surviving token refused. Refused while he drives passengers.
    public static func suspendUser(_ userId: String, reason: String? = nil) -> Endpoint<UserDecision> {
        struct Body: Encodable { let reason: String? }
        return .post("admin/users/\(userId)/suspend", body: Body(reason: clean(reason)))
    }

    /// require_operations.
    public static func reinstateUser(_ userId: String, reason: String? = nil) -> Endpoint<UserDecision> {
        struct Body: Encodable { let reason: String? }
        return .post("admin/users/\(userId)/reinstate", body: Body(reason: clean(reason)))
    }

    // MARK: The record

    /// require_admin. Newest first. Paged: `sendWithMeta` for the total.
    public static func audit(
        action: String? = nil, entityType: String? = nil, actorId: String? = nil, limit: Int = 50, offset: Int = 0
    ) -> Endpoint<[AuditEntry]> {
        var query: [URLQueryItem] = []
        if let action { query.append(URLQueryItem(name: "action", value: action)) }
        if let entityType { query.append(URLQueryItem(name: "entity_type", value: entityType)) }
        if let actorId { query.append(URLQueryItem(name: "actor_id", value: actorId)) }
        query.append(URLQueryItem(name: "limit", value: String(limit)))
        query.append(URLQueryItem(name: "offset", value: String(offset)))
        return .get("admin/audit", query: query)
    }

    // MARK: -

    private struct ReviewBody: Encodable {
        let verified: Bool
        let rejectionReason: String?
        let expiresOn: String?
    }

    /// Blank is absent: the server stores null, never "".
    private static func clean(_ text: String?) -> String? {
        let trimmed = text?.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed?.isEmpty == false ? trimmed : nil
    }
}
