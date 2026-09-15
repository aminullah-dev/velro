import Observation
import SwiftUI
import VelroCore
#if canImport(UIKit)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

/// One passenger: who he is, how he travels in figures, his latest bookings,
/// what he is asking for now and what he has told support -- and suspending
/// the account, or putting a suspended one back.
///
/// Loads him by id, so another screen can open him without the directory's
/// list. Every list here is narrowed to his id on this side too: a server
/// before these filters answers everybody's, and a stranger's booking must
/// never read as his. On such a server the page shows what the directory's
/// row knew, with one calm line about the rest.
struct OpPassengerDetailView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    let userId: String
    /// The directory's row, shown until his page arrives (and in its place
    /// on a server without one).
    let initial: AdminUser?
    /// The directory again, after a decision changed him.
    let onChanged: @MainActor @Sendable () async -> Void

    @State private var model: OpPassengerModel
    @State private var confirm: ConfirmRequest?

    init(userId: String, initial: AdminUser?, onChanged: @escaping @MainActor @Sendable () async -> Void) {
        self.userId = userId
        self.initial = initial
        self.onChanged = onChanged
        _model = State(initialValue: OpPassengerModel(userId: userId))
    }

    private var user: AdminUser? { model.user ?? initial }

    var body: some View {
        Group {
            if let user {
                content(user)
            } else if let failure = model.failure {
                if failure.isEndpointMissing {
                    EmptyStateView(messageKey: "ops.passengers.needs_server_update", systemImage: "info.circle")
                } else {
                    ErrorView(error: failure) { [model, ops] in await model.load(ops) }
                }
            } else {
                LoadingView()
            }
        }
        .background(Palette.background)
        .opNavigationTitle(user.map { OpText.name($0.fullName, strings) } ?? "")
        .poll(every: .seconds(60)) { [model, ops] in await model.load(ops) }
        .confirmAction($confirm)
    }

    // MARK: The page

    private func content(_ user: AdminUser) -> some View {
        Form {
            Section {
                OpDetailTitle(OpText.name(user.fullName, strings)) {
                    StatusChip(user: user.status)
                    if user.isDriver { StatusChip(role: AccountRole.driver.rawValue) }
                    ForEach(StaffAccess(roles: user.roles).staffRoles, id: \.self) { role in
                        StatusChip(role: role.rawValue)
                    }
                }
                .padding(.vertical, Spacing.s2)
            }
            if model.needsServerUpdate {
                Section {
                    Label(strings["ops.passengers.needs_server_update"], systemImage: "info.circle")
                        .opsFont(.caption)
                        .foregroundStyle(Palette.textMuted)
                }
            }
            about(user)
            if let summary = model.detail?.passenger {
                figures(summary)
            }
            bookingsSection
            requestsSection
            ticketsSection
            if let driverId = model.detail?.driverId {
                Section {
                    Button {
                        ops.navigator.open(.drivers, filter: "driver:" + driverId)
                    } label: {
                        Label(strings["ops.passengers.open_driver"], systemImage: Route.drivers.symbol)
                    }
                    .accessibilityIdentifier("passenger.driver")
                } header: {
                    OpFormHeader(titleKey: "ops.passengers.also_driver")
                }
            }
            if ops.can(.audit) {
                Section {
                    Button {
                        ops.navigator.open(.audit, filter: "actor:" + user.id)
                    } label: {
                        Label(strings["ops.audit.only_this_actor"], systemImage: Route.audit.symbol)
                    }
                } header: {
                    OpFormHeader(titleKey: "admin.nav.audit")
                }
            }
            actions(user)
        }
        .formStyle(.grouped)
        .scrollContentBackground(.hidden)
    }

    private func about(_ user: AdminUser) -> some View {
        Section {
            // Not an OpField: that one reads as a single element, and the
            // copy button must stay a button of its own for VoiceOver.
            LabeledContent {
                HStack(spacing: Spacing.s3) {
                    PhoneLink(user.phone)
                    if let phone = user.phone, !phone.isEmpty {
                        OpCopyButton(text: phone, labelKey: "ops.passengers.copy_phone")
                    }
                }
                .opsFont(.body)
            } label: {
                Text(strings["admin.col.phone"])
                    .opsFont(.label, weight: .regular)
                    .foregroundStyle(Palette.textMuted)
            }
            OpField("passenger.profile.since") { DateText(user.createdAt, style: .date) }
            OpField("ops.passengers.last_active", text: OpPassengerText.lastActive(user, strings))
            OpField("passenger.profile.language", text: AppLocale(tag: user.locale).endonym)
            OpField("admin.col.rating", text: OpText.rating(user.ratingAverage, count: user.ratingCount, strings))
            if let summary = model.detail?.passenger {
                if let first = summary.firstBookingAt {
                    OpField("ops.passengers.first_booking") { DateText(first, style: .date) }
                }
                if let last = summary.lastBookingAt {
                    OpField("ops.passengers.last_booking") { DateText(last, style: .relative) }
                }
            }
        }
    }

    /// His history in figures, as the dashboard's cards.
    private func figures(_ s: PassengerSummary) -> some View {
        Section {
            DashGrid(minimum: 140) {
                StatCard("admin.nav.bookings", count: s.bookingsTotal, systemImage: "ticket")
                StatCard("booking.status.completed", count: s.bookingsCompleted)
                StatCard("booking.status.cancelled", count: s.bookingsCancelled)
                // A habit of not turning up is what an operator is asked about.
                StatCard("booking.status.no_show", count: s.noShows, attention: true)
                    .note(s.bookingsTotal > 0 && s.noShows > 0 ? OpsFormat.fraction(s.noShows, of: s.bookingsTotal, strings) : nil)
                StatCard("admin.col.seats", count: s.seatsBooked)
                StatCard("ops.passengers.spent", money: s.spent)
                StatCard("ops.passengers.requests_total", count: s.rideRequestsTotal)
                StatCard("ops.passengers.open_requests", count: s.openRideRequests,
                         action: s.openRideRequests > 0 ? act(.liveRequests) : nil)
                StatCard("admin.stat.open_tickets", count: s.ticketsOpen, attention: true)
                StatCard("ops.passengers.tickets_total", count: s.ticketsTotal)
            }
            .padding(.vertical, Spacing.s1)
            .listRowInsets(EdgeInsets())
            .listRowBackground(Color.clear)
        }
    }

    // MARK: What he has done

    @ViewBuilder
    private var bookingsSection: some View {
        // On a server that cannot narrow them, only rows that name him are
        // his -- and none do; an empty section there would claim he has none.
        if model.isCurrentServer || !model.bookings.isEmpty {
            Section {
                if model.bookings.isEmpty {
                    Text(strings["ops.passengers.no_bookings"])
                        .opsFont(.body)
                        .foregroundStyle(Palette.textMuted)
                } else {
                    ForEach(model.bookings) { booking in
                        Button {
                            ops.navigator.open(.trips, filter: "trip:" + booking.tripNumber)
                        } label: {
                            OpPassengerBookingLine(booking: booking)
                        }
                        .buttonStyle(.plain)
                        .disabled(!ops.can(.trips))
                    }
                }
            } header: {
                OpFormHeader(titleKey: "ops.passengers.recent_bookings")
            } footer: {
                if let total = model.bookingsTotal, total > model.bookings.count {
                    Text(strings["admin.showing", ["from": 1, "to": model.bookings.count, "total": total]])
                        .opsFont(.caption)
                        .foregroundStyle(Palette.textMuted)
                }
            }
        }
    }

    /// Only what is open now: the board the office watches (admin/ride-requests)
    /// holds open, unexpired requests and nothing else. His history of
    /// requests is the count among the figures above.
    @ViewBuilder
    private var requestsSection: some View {
        if !model.requests.isEmpty {
            Section {
                ForEach(model.requests) { request in
                    Button {
                        ops.navigator.open(.liveRequests, filter: "request:" + request.id)
                    } label: {
                        OpPassengerRequestLine(request: request)
                    }
                    .buttonStyle(.plain)
                    .disabled(!ops.can(.liveRequests))
                }
            } header: {
                OpFormHeader(titleKey: "ops.passengers.open_requests")
            }
        }
    }

    /// Support requests are the support desk's to read: shown only to the
    /// roles that may open them.
    @ViewBuilder
    private var ticketsSection: some View {
        if ops.can(.support), model.isCurrentServer || !model.tickets.isEmpty {
            Section {
                if model.tickets.isEmpty {
                    Text(strings["ops.passengers.no_tickets"])
                        .opsFont(.body)
                        .foregroundStyle(Palette.textMuted)
                } else {
                    ForEach(model.tickets) { ticket in
                        Button {
                            ops.navigator.open(.support, filter: "ticket:" + ticket.id)
                        } label: {
                            OpPassengerTicketLine(ticket: ticket)
                        }
                        .buttonStyle(.plain)
                    }
                }
            } header: {
                OpFormHeader(titleKey: "admin.support.title")
            }
        }
    }

    // MARK: Decisions

    /// Suspend or reinstate. Not offered for a staff account: locking a
    /// colleague out is not a passenger decision, and this screen must never
    /// be where an operator signs himself out.
    @ViewBuilder
    private func actions(_ user: AdminUser) -> some View {
        if !user.isStaff {
            switch user.status {
            case .active:
                Section {
                    Button(role: .destructive) { askSuspend(user) } label: {
                        Label(strings["admin.action.suspend"], systemImage: "hand.raised.slash")
                    }
                    .accessibilityIdentifier("passenger.suspend")
                } footer: {
                    Text(strings["ops.passengers.suspend_hint"])
                        .opsFont(.caption)
                        .foregroundStyle(Palette.textMuted)
                }
            case .suspended:
                Section {
                    Button { askReinstate(user) } label: {
                        Label(strings["ops.passengers.reinstate"], systemImage: "arrow.uturn.backward.circle")
                    }
                    .accessibilityIdentifier("passenger.reinstate")
                } footer: {
                    Text(strings["ops.passengers.reinstate_hint"])
                        .opsFont(.caption)
                        .foregroundStyle(Palette.textMuted)
                }
            case .deactivated:
                EmptyView()
            }
        }
    }

    private func askSuspend(_ user: AdminUser) {
        let id = user.id
        confirm = ConfirmRequest(
            title: strings["ops.passengers.suspend_confirm"],
            message: OpText.name(user.fullName, strings) + " — " + strings["ops.passengers.suspend_hint"],
            confirmTitle: strings["admin.action.suspend"],
            isDestructive: true,
            reason: .required,
            reasonPrompt: strings["ops.passengers.suspend_reason"]
        ) { [ops, model, onChanged] reason in
            switch await ops.send(AdminAPI.suspendUser(id, reason: reason)) {
            case .success:
                await model.load(ops)
                await onChanged()
                await ops.refreshAttention()
                return nil
            case .failure(let error):
                return error
            }
        }
    }

    private func askReinstate(_ user: AdminUser) {
        let id = user.id
        confirm = ConfirmRequest(
            title: strings["ops.passengers.reinstate_confirm"],
            message: OpText.name(user.fullName, strings) + " — " + strings["ops.passengers.reinstate_hint"],
            confirmTitle: strings["ops.passengers.reinstate"],
            reason: .required,
            reasonPrompt: strings["ops.passengers.reinstate_reason"]
        ) { [ops, model, onChanged] reason in
            switch await ops.send(AdminAPI.reinstateUser(id, reason: reason)) {
            case .success:
                await model.load(ops)
                await onChanged()
                await ops.refreshAttention()
                return nil
            case .failure(let error):
                return error
            }
        }
    }

    /// Opens a place -- only where these roles may go.
    private func act(_ route: Route, _ filter: String? = nil) -> (() -> Void)? {
        guard ops.can(route) else { return nil }
        let navigator = ops.navigator
        return { navigator.open(route, filter: filter) }
    }
}

// MARK: - The model

@MainActor
@Observable
final class OpPassengerModel {
    let userId: String
    /// His page, from admin/users/{id}.
    private(set) var detail: UserDetail?
    /// Nothing to show and the page failed.
    private(set) var failure: APIError?
    /// The server predates his page: what shows is the directory's row.
    private(set) var needsServerUpdate = false
    private(set) var bookings: [AdminBooking] = []
    /// The server's count of his bookings, when it narrowed them to him.
    private(set) var bookingsTotal: Int?
    private(set) var tickets: [AdminTicket] = []
    private(set) var requests: [AdminRideRequest] = []

    static let recentBookings = 20

    init(userId: String) { self.userId = userId }

    var user: AdminUser? { detail?.user }
    /// A server that knows his page also narrows the lists to him, so an
    /// empty one means he has none.
    var isCurrentServer: Bool { detail != nil }

    func load(_ ops: OpsModel) async {
        let id = userId
        async let page = ops.send(AdminAPI.user(id))
        async let recent = ops.sendWithMeta(AdminAPI.bookings(passengerId: id, limit: Self.recentBookings))
        async let live = ops.send(AdminAPI.rideRequests(passengerId: id, limit: 50))
        var raised: Result<SupportQueue, APIError>?
        if ops.can(.support) {
            raised = await ops.send(AdminAPI.supportTickets(.all, reporterId: id, limit: 50))
        }

        switch await page {
        case .success(let value):
            detail = value
            failure = nil
            needsServerUpdate = false
        case .failure(let error):
            if error == .cancelled { return }
            needsServerUpdate = error.isEndpointMissing
            // A failed refresh keeps what is on screen.
            if detail == nil { failure = error }
        }
        if case .success(let answer) = await recent {
            bookings = answer.items.filter { $0.passengerId == id }
            bookingsTotal = isCurrentServer ? answer.meta.total : nil
        }
        if case .success(let rows) = await live {
            requests = rows.filter { $0.passengerId == id }
        }
        if case .success(let queue)? = raised {
            tickets = queue.tickets.filter { $0.reporterId == id }
        }
    }
}

// MARK: - Lines

private struct OpPassengerBookingLine: View {
    @Environment(\.strings) private var strings
    let booking: AdminBooking

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            HStack(spacing: Spacing.s2) {
                LTRText(booking.number)
                    .opsFont(.label, weight: .medium)
                    .foregroundStyle(Palette.text)
                StatusChip(booking: booking.status)
                Spacer(minLength: 0)
                MoneyText(booking.fare)
                    .opsFont(.label, weight: .medium)
                    .foregroundStyle(Palette.text)
            }
            HStack(spacing: Spacing.s2) {
                Image(systemName: Route.trips.symbol).accessibilityHidden(true)
                LTRText(booking.tripNumber)
                DotSeparator().accessibilityHidden(true)
                Label(OpsFormat.count(booking.seatCount, strings), systemImage: "person.fill")
                    .accessibilityLabel(strings["admin.col.seats"] + " " + OpsFormat.count(booking.seatCount, strings))
                Spacer(minLength: 0)
                DateText(booking.createdAt, style: .relative)
            }
            .opsFont(.caption)
            .foregroundStyle(Palette.textMuted)
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("passenger.booking." + booking.number)
    }
}

private struct OpPassengerRequestLine: View {
    @Environment(\.strings) private var strings
    let request: AdminRideRequest

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            HStack(spacing: Spacing.s2) {
                Text(OpText.route(request.originStationName, request.destinationName, strings))
                    .opsFont(.body, weight: .medium)
                    .foregroundStyle(Palette.text)
                    .lineLimit(2)
                Spacer(minLength: 0)
                MoneyText(request.offeredFare)
                    .opsFont(.label, weight: .medium)
                    .foregroundStyle(Palette.text)
            }
            HStack(spacing: Spacing.s2) {
                if request.isUnanswered {
                    StatusChip(strings["admin.negotiations.no_offers"], tone: .attention)
                } else {
                    StatusChip(strings["home.open_request.offers", ["count": request.offerCount]], tone: .active)
                }
                DateText(request.requestedFor)
                Spacer(minLength: 0)
                DateText(request.createdAt, style: .relative)
            }
            .opsFont(.caption)
            .foregroundStyle(Palette.textMuted)
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

private struct OpPassengerTicketLine: View {
    @Environment(\.strings) private var strings
    let ticket: AdminTicket

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            HStack(spacing: Spacing.s2) {
                // Urgency carries a word, not only a colour.
                if ticket.isUrgent {
                    StatusChip(strings["admin.support.urgent"], tone: .failed)
                }
                Text(OpText.word(ticket.categoryKey, raw: ticket.categoryCode, strings))
                    .opsFont(.body, weight: .medium)
                    .foregroundStyle(Palette.text)
                    .lineLimit(1)
                Spacer(minLength: 0)
                StatusChip(ticket: ticket.status)
            }
            HStack(spacing: Spacing.s2) {
                LTRText(ticket.reference)
                Spacer(minLength: 0)
                DateText(ticket.createdAt, style: .relative)
            }
            .opsFont(.caption)
            .foregroundStyle(Palette.textMuted)
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

/// Copies a value, and says so for a moment with a tick.
struct OpCopyButton: View {
    @Environment(\.strings) private var strings
    let text: String
    let labelKey: String
    @State private var copied = false

    var body: some View {
        Button {
            #if canImport(UIKit)
            UIPasteboard.general.string = text
            #elseif canImport(AppKit)
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(text, forType: .string)
            #endif
            copied = true
            Task { @MainActor in
                try? await Task.sleep(for: .seconds(1.5))
                copied = false
            }
        } label: {
            Image(systemName: copied ? "checkmark" : "doc.on.doc")
                .foregroundStyle(copied ? Palette.accent : Palette.textMuted)
                .contentTransition(.symbolEffect(.replace))
        }
        .buttonStyle(.borderless)
        .accessibilityLabel(strings[labelKey])
        .help(strings[labelKey])
    }
}
