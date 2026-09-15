import Observation
import SwiftUI
import VelroCore

/// The passenger directory: everyone who travels, found by name or phone,
/// narrowed to the active or the suspended, and scrolling on past the first
/// page. Beside the list on iPad and Mac, pushed on an iPhone.
///
/// Other screens open it with `navigator.open(.passengers, filter:)`:
/// "passenger:<user id>" (selects him), "search:<text>", "suspended",
/// "active", "all".
///
/// A server before admin/users learned role, search and paging answers
/// every account in one page and no total: the list then keeps the
/// passengers itself, searches what it holds, and says once, calmly, that
/// the rest comes with the server's update.
struct PassengersView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @State private var model = OpPassengersModel()
    @State private var selectedID: String?
    /// A passenger another screen asked for, pushed on an iPhone.
    @State private var pushedID: String?

    init() {}

    var body: some View {
        OpSplitReader { isSplit in
            if isSplit {
                OpSplitLayout(listWidth: 420) {
                    list(isSplit: true)
                } detail: {
                    if let id = selectedID {
                        detail(id).id(id)
                    } else {
                        OpNothingSelected(messageKey: "ops.passengers.choose", systemImage: Route.passengers.symbol)
                    }
                }
            } else {
                list(isSplit: false)
                    .navigationDestination(for: AdminUser.self) { user in detail(user.id) }
                    .navigationDestination(item: $pushedID) { id in detail(id) }
            }
        }
        .background(Palette.background)
        .navigationTitle(strings["admin.stat.passengers"])
        .searchable(text: Binding(get: { model.search }, set: { model.search = $0 }),
                    prompt: Text(strings["ops.passengers.search"]))
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                OpRefreshButton { [model] in await model.pager.refresh() }
            }
        }
        .task { [model, ops] in
            let chosen = model.apply(deepLink: ops.navigator.takeFilter(for: .passengers))
            // Beside the list he is selected at once: his page loads him by id.
            if let chosen { selectedID = chosen }
            await model.reload(ops)
            // On an iPhone he is opened once the directory stands behind him,
            // not in the frame this screen itself is being pushed.
            if let chosen { pushedID = chosen }
        }
        // A moment after the typing stops, the server is asked; the newest
        // question wins (the pager drops an older answer).
        .task(id: model.search) { [model, ops] in
            guard model.searchChanged else { return }
            try? await Task.sleep(for: .milliseconds(350))
            guard !Task.isCancelled else { return }
            await model.searchAgain(ops)
        }
        // The directory barely moves; a status changed elsewhere shows within a minute.
        .poll(every: .seconds(60)) { [model] in await model.pager.refresh() }
    }

    private func detail(_ id: String) -> some View {
        OpPassengerDetailView(userId: id, initial: model.user(id)) { [model] in await model.pager.refresh() }
    }

    private var sliceBinding: Binding<OpPassengersModel.Slice> {
        Binding(get: { model.slice }, set: { value in
            guard value != model.slice else { return }
            model.slice = value
            selectedID = nil
            Task { [model, ops] in await model.reload(ops) }
        })
    }

    @ViewBuilder
    private func list(isSplit: Bool) -> some View {
        VStack(spacing: 0) {
            OpChipBar(options: OpPassengersModel.Slice.allCases.map { .init(value: $0, label: $0.label(strings)) },
                      selection: sliceBinding)
            if model.isLegacyServer {
                Banner(strings["ops.passengers.needs_server_update"], tone: .info, systemImage: "info.circle")
                    .padding(.horizontal, Spacing.s4)
                    .padding(.bottom, Spacing.s2)
            }
            Divider()
            let pager = model.pager
            let shown = model.shown
            if pager.isFirstLoad {
                LoadingView()
            } else if let error = pager.error {
                ErrorView(error: error) { [model, ops] in await model.reload(ops) }
            } else if shown.isEmpty {
                EmptyStateView(messageKey: model.isFiltered ? "ops.passengers.none" : "ops.passengers.empty",
                               systemImage: Route.passengers.symbol)
            } else {
                List(selection: isSplit ? $selectedID : .constant(nil)) {
                    ForEach(shown) { user in
                        if isSplit {
                            OpPassengerRow(user: user).tag(user.id)
                        } else {
                            NavigationLink(value: user) { OpPassengerRow(user: user) }
                        }
                    }
                    OpPagerFooter(pager: pager)
                }
                .listStyle(.plain)
                // Selected beside its detail: a light ground the row's own ink reads on.
                .tint(isSplit ? Palette.bannerInfo : Palette.accent)
                .scrollContentBackground(.hidden)
                .refreshable { await pager.refresh() }
            }
        }
    }
}

// MARK: - The model

@MainActor
@Observable
final class OpPassengersModel {
    enum Slice: CaseIterable, Hashable {
        case all, active, suspended

        var status: UserStatus? {
            switch self {
            case .all: nil
            case .active: .active
            case .suspended: .suspended
            }
        }

        func label(_ strings: Strings) -> String {
            switch self {
            case .all: strings["admin.filter.all"]
            case .active: strings["ops.passengers.status.active"]
            case .suspended: strings["ops.passengers.status.suspended"]
            }
        }
    }

    var slice: Slice = .all
    var search = ""
    let pager = OpPager<AdminUser>(pageSize: 50)
    /// The search the list on screen answers; nil before the first load.
    private(set) var asked: String?

    var query: String { search.trimmingCharacters(in: .whitespacesAndNewlines) }
    var isFiltered: Bool { slice != .all || !query.isEmpty }
    /// Typing moved on from the question the list answers.
    var searchChanged: Bool { asked != nil && asked != query }

    /// Today's production server: admin/users without role, search or
    /// offset, and a meta with no total. Every paged answer of the current
    /// one carries its total, even when it is zero.
    var isLegacyServer: Bool { pager.hasLoaded && pager.total == nil }

    var shown: [AdminUser] {
        guard isLegacyServer else { return pager.items }
        let query = query
        let status = slice.status
        return pager.items.filter { user in
            user.isPassenger && (status == nil || user.status == status) && (query.isEmpty || Self.matches(user, query))
        }
    }

    func user(_ id: String?) -> AdminUser? {
        guard let id else { return nil }
        return pager.items.first { $0.id == id }
    }

    /// The filter another screen left; a passenger to open comes back.
    func apply(deepLink: String?) -> String? {
        guard let deepLink else { return nil }
        let parts = deepLink.split(separator: ":", maxSplits: 1).map(String.init)
        let value = parts.count > 1 ? parts[1] : ""
        switch parts.first?.lowercased() {
        case "passenger", "user": return value.isEmpty ? nil : value
        case "search": search = value
        case "suspended": slice = .suspended
        case "active": slice = .active
        case "all": slice = .all
        default: break
        }
        return nil
    }

    func reload(_ ops: OpsModel) async {
        let query = query
        asked = query
        let status = slice.status
        let search: String? = query.isEmpty ? nil : query
        await pager.reload { [ops] limit, offset in
            await ops.sendWithMeta(AdminAPI.users(role: .passenger, search: search, status: status, limit: limit, offset: offset))
        }
    }

    /// The server is asked again for the new search -- unless it is one that
    /// cannot search, where the rows already here are searched instead.
    func searchAgain(_ ops: OpsModel) async {
        if isLegacyServer {
            asked = query
        } else {
            await reload(ops)
        }
    }

    /// On a server that cannot search: a name in any Persian letter form, or
    /// three digits or more of the phone in any form.
    static func matches(_ user: AdminUser, _ query: String) -> Bool {
        if let name = user.fullName, PlaceNames.matches(name, query) { return true }
        let digits = Numerals.latin(query).filter(\.isNumber)
        guard digits.count >= 3, let phone = user.phone else { return false }
        return phone.filter(\.isNumber).contains(digits.drop(while: { $0 == "0" }))
    }
}

// MARK: - A row

private struct OpPassengerRow: View {
    @Environment(\.strings) private var strings
    let user: AdminUser

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            HStack(spacing: Spacing.s2) {
                Text(OpText.name(user.fullName, strings))
                    .opsFont(.heading, weight: .medium)
                    .foregroundStyle(Palette.text)
                    .lineLimit(1)
                Spacer(minLength: 0)
                if user.isDriver { StatusChip(role: AccountRole.driver.rawValue) }
                StatusChip(user: user.status)
            }
            HStack(spacing: Spacing.s2) {
                if let phone = user.phone { LTRText(phone) } else { Text("—") }
                DotSeparator().accessibilityHidden(true)
                Text(OpText.rating(user.ratingAverage, count: user.ratingCount, strings))
            }
            .opsFont(.body)
            .foregroundStyle(Palette.textMuted)
            HStack(spacing: Spacing.s2) {
                if let since = OpsFormat.format(user.createdAt, style: .date, strings: strings) {
                    Text(strings["passenger.profile.since"] + " " + since)
                        .lineLimit(1)
                    DotSeparator().accessibilityHidden(true)
                }
                Label(OpPassengerText.lastActive(user, strings), systemImage: "clock")
                    .lineLimit(1)
                    .accessibilityLabel(strings["ops.passengers.last_active"] + " " + OpPassengerText.lastActive(user, strings))
            }
            .opsFont(.caption)
            .foregroundStyle(Palette.textMuted)
        }
        .padding(.vertical, Spacing.s1)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("passengers.row." + (user.phone ?? user.id))
    }
}

// MARK: - Shared with the other screens

enum OpPassengerText {
    /// "5 min ago", "3 days ago", or "Never".
    static func lastActive(_ user: AdminUser, _ strings: Strings) -> String {
        guard let seen = user.lastSeen else { return strings["common.value.never"] }
        return OpsFormat.relative(seen, strings)
    }
}

extension StatusChip {
    /// An account's status as a word: Active, Suspended, Account closed.
    init(user status: UserStatus) {
        let key = switch status {
        case .active: "ops.passengers.status.active"
        case .suspended: "ops.passengers.status.suspended"
        case .deactivated: "ops.passengers.status.deactivated"
        }
        self.init(key: key, raw: status.rawValue, tone: status.tone)
    }
}

/// A passenger's name that opens his page -- where the server said who he is
/// and these roles may open it; otherwise the name alone.
struct OpPassengerLink: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    let userId: String?
    let name: String?

    var body: some View {
        let title = OpText.name(name, strings)
        if let userId, ops.can(.passengers) {
            Button {
                ops.navigator.open(.passengers, filter: "passenger:" + userId)
            } label: {
                Label(title, systemImage: Route.passengers.symbol)
                    .labelStyle(.titleAndIcon)
                    .foregroundStyle(Palette.accent)
            }
            .buttonStyle(.borderless)
            .accessibilityHint(strings["ops.passengers.open"])
        } else {
            Text(title)
        }
    }
}

extension View {
    /// "Open the passenger's page" on a row's context menu, when the row
    /// knows whose it is and these roles may open it.
    func opPassengerMenu(_ userId: String?) -> some View {
        modifier(OpPassengerMenu(userId: userId))
    }
}

private struct OpPassengerMenu: ViewModifier {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    let userId: String?

    @ViewBuilder
    func body(content: Content) -> some View {
        if let userId, ops.can(.passengers) {
            content.contextMenu {
                Button {
                    ops.navigator.open(.passengers, filter: "passenger:" + userId)
                } label: {
                    Label(strings["ops.passengers.open"], systemImage: Route.passengers.symbol)
                }
            }
        } else {
            content
        }
    }
}
