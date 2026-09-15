import Observation
import SwiftUI
import VelroCore

/// The driver directory (the panel's Drivers.tsx): everyone registered to
/// drive, found by name, phone or plate, narrowed by approval and by whether
/// he is working -- and "without a fix", the working drivers the office cannot
/// place, which the dashboard's card opens directly.
///
/// Other screens open it with `navigator.open(.drivers, filter:)`:
/// "stale_gps", "pending", "approved", "suspended", "rejected", "online",
/// "on_trip", "offline", "driver:<driver id>" (selects him), "search:<text>".
struct DriversView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @State private var model = OpDriversModel()
    @State private var selectedID: String?
    /// A driver another screen asked for, pushed on an iPhone.
    @State private var pushed: AdminDriver?

    init() {}

    var body: some View {
        OpSplitReader { isSplit in
            if isSplit {
                OpSplitLayout(listWidth: 420) {
                    list(isSplit: true)
                } detail: {
                    if let driver = model.driver(selectedID) {
                        OpDriverDetailView(driver: driver) { [model, ops] in await model.load(ops) }
                            .id(driver.id)
                    } else {
                        OpNothingSelected(messageKey: "ops.drivers.choose", systemImage: "steeringwheel")
                    }
                }
            } else {
                list(isSplit: false)
                    .navigationDestination(for: AdminDriver.self) { driver in
                        OpDriverDetailView(driver: model.driver(driver.id) ?? driver) { [model, ops] in await model.load(ops) }
                    }
                    .navigationDestination(item: $pushed) { driver in
                        OpDriverDetailView(driver: model.driver(driver.id) ?? driver) { [model, ops] in await model.load(ops) }
                    }
            }
        }
        .background(Palette.background)
        .navigationTitle(strings["admin.nav.drivers"])
        .searchable(text: Binding(get: { model.search }, set: { model.search = $0 }),
                    prompt: Text(strings["ops.drivers.search"]))
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                OpRefreshButton { [model, ops] in await model.load(ops) }
            }
        }
        .task { [model, ops] in
            let chosen = model.apply(deepLink: ops.navigator.takeFilter(for: .drivers))
            if let chosen { selectedID = chosen }
            await model.load(ops)
            // Beside the list he is selected; on an iPhone he is opened.
            if let chosen, let driver = model.driver(chosen) { pushed = driver }
        }
        // "Without a fix" is watched, as in the panel; the directory itself
        // barely moves.
        .poll(every: .seconds(20)) { [model, ops] in
            await model.tick(ops)
        }
        // A moment after the typing stops, the server is asked too.
        .task(id: model.search) { [model, ops] in
            try? await Task.sleep(for: .milliseconds(350))
            guard !Task.isCancelled else { return }
            await model.searchServer(ops)
        }
    }

    private var approvalBinding: Binding<DriverApprovalStatus?> {
        Binding(get: { model.approval }, set: { model.approval = $0 })
    }

    private var presenceBinding: Binding<OpDriversModel.Presence> {
        Binding(get: { model.presence }, set: { value in
            let wasStale = model.presence == .stale
            model.presence = value
            if wasStale != (value == .stale) {
                Task { [model, ops] in await model.reloadFromScratch(ops) }
            }
        })
    }

    @ViewBuilder
    private func list(isSplit: Bool) -> some View {
        VStack(spacing: 0) {
            let all = model.state.value ?? []
            OpChipBar(options: [.init(value: DriverApprovalStatus?.none, label: strings["admin.filter.all"], count: all.count)]
                      + OpDriversModel.approvals.map { status in
                          .init(value: DriverApprovalStatus?.some(status),
                                label: OpText.word(status.messageKey, raw: status.rawValue, strings),
                                count: all.filter { $0.approvalStatus == status }.count)
                      },
                      selection: approvalBinding)
            OpChipBar(options: OpDriversModel.Presence.allCases.map { presence in
                .init(value: presence, label: presence.label(strings),
                      count: presence == .any || presence == .stale ? nil : all.filter(presence.matches).count)
            }, selection: presenceBinding)
            Divider()
            switch model.state {
            case .loading:
                LoadingView()
            case .failed(let error):
                ErrorView(error: error) { [model, ops] in await model.load(ops) }
            case .loaded:
                let shown = model.shown
                if shown.isEmpty {
                    EmptyStateView(messageKey: model.isFiltered ? "ops.drivers.none" : "admin.empty.drivers",
                                   systemImage: "steeringwheel")
                } else {
                    List(selection: isSplit ? $selectedID : .constant(nil)) {
                        ForEach(shown) { driver in
                            Group {
                                if isSplit {
                                    OpDriverRowView(driver: driver, flagStale: model.presence == .stale).tag(driver.id)
                                } else {
                                    NavigationLink(value: driver) {
                                        OpDriverRowView(driver: driver, flagStale: model.presence == .stale)
                                    }
                                }
                            }
                            .opAttentionRow(model.presence == .stale)
                        }
                        Text(strings["admin.showing", [
                            "from": 1, "to": shown.count,
                            // Unfiltered, the server's own count: the list is its first page.
                            "total": model.isFiltered ? shown.count : max(model.total ?? shown.count, shown.count),
                        ]])
                            .opsFont(.caption)
                            .foregroundStyle(Palette.textMuted)
                            .frame(maxWidth: .infinity)
                            .listRowSeparator(.hidden)
                    }
                    .listStyle(.plain)
                    // Selected beside its detail: a light ground the row's own ink reads on.
                    .tint(isSplit ? Palette.bannerInfo : Palette.accent)
                    .scrollContentBackground(.hidden)
                    .refreshable { [model, ops] in await model.load(ops) }
                }
            }
        }
    }
}

// MARK: - The model

@MainActor
@Observable
final class OpDriversModel {
    static let approvals: [DriverApprovalStatus] = [.approved, .pending, .suspended, .rejected]

    /// Whether he is working, and whether the office can place him.
    enum Presence: CaseIterable, Hashable {
        case any, online, onTrip, offline, stale

        func label(_ strings: Strings) -> String {
            switch self {
            case .any: strings["admin.filter.all"]
            case .online: strings["driver.status.online"]
            case .onTrip: strings["admin.map.on_trip"]
            case .offline: strings["driver.status.offline"]
            case .stale: strings["admin.filter.stale_gps"]
            }
        }

        func matches(_ driver: AdminDriver) -> Bool {
            switch self {
            case .any, .stale: true
            case .online: driver.availability == .online || driver.availability == .busy
            case .onTrip: driver.availability == .onTrip
            case .offline: driver.availability == .offline
            }
        }
    }

    private(set) var state: LoadState<[AdminDriver]> = .loading
    /// How many drivers the server has in all: the list holds the first 200.
    private(set) var total: Int?
    /// The server's own matches for the search, from past those 200.
    private(set) var found: [AdminDriver] = []
    var approval: DriverApprovalStatus?
    /// `.stale` is the server's own filter (`stale_gps`); the rest narrow
    /// what is loaded.
    var presence: Presence = .any
    var search = ""
    private var ticks = 0
    private var generation = 0

    var isFiltered: Bool { approval != nil || presence != .any || !query.isEmpty }

    private var query: String { search.trimmingCharacters(in: .whitespacesAndNewlines) }

    var shown: [AdminDriver] {
        let drivers = state.value ?? []
        let query = query
        let digits = Numerals.latin(query).filter(\.isNumber)
        let plateQuery = OpDriversModel.plateKey(query)
        let local = drivers.filter { driver in
            if let approval, driver.approvalStatus != approval { return false }
            if !presence.matches(driver) { return false }
            guard !query.isEmpty else { return true }
            if let name = driver.fullName, PlaceNames.matches(name, query) { return true }
            if digits.count >= 3, let phone = driver.phone, phone.filter(\.isNumber).contains(digits.drop(while: { $0 == "0" })) {
                return true
            }
            if !plateQuery.isEmpty, let plate = driver.plateNumber, OpDriversModel.plateKey(plate).contains(plateQuery) {
                return true
            }
            return false
        }
        guard !query.isEmpty else { return local }
        // The server matched these past the loaded page; the device's own
        // matching (Persian letter forms, plates) keeps its share first.
        let seen = Set(local.map(\.id))
        let more = found.filter { driver in
            !seen.contains(driver.id) && (approval == nil || driver.approvalStatus == approval) && presence.matches(driver)
        }
        return local + more
    }

    func driver(_ id: String?) -> AdminDriver? {
        guard let id else { return nil }
        return state.value?.first { $0.id == id } ?? found.first { $0.id == id }
    }

    /// Asks the server for the search, so a driver past the first 200 is
    /// found too. The newest question wins.
    func searchServer(_ ops: OpsModel) async {
        let asked = query
        guard !asked.isEmpty else { found = []; return }
        let result = await ops.send(AdminAPI.drivers(staleGPS: presence == .stale, search: asked, limit: 100))
        guard asked == query else { return }
        if case .success(let drivers) = result { found = drivers }
    }

    /// The filter another screen left; a driver to select comes back.
    func apply(deepLink: String?) -> String? {
        guard let deepLink else { return nil }
        let parts = deepLink.split(separator: ":", maxSplits: 1).map(String.init)
        let value = parts.count > 1 ? parts[1] : ""
        switch parts.first?.lowercased() {
        case "stale_gps", "stale": presence = .stale
        case "online": presence = .online
        case "on_trip": presence = .onTrip
        case "offline": presence = .offline
        case "driver": return value.isEmpty ? nil : value
        case "search": search = value
        case let other?:
            if let status = DriverApprovalStatus(rawValue: other.uppercased()) { approval = status }
        case nil: break
        }
        return nil
    }

    func load(_ ops: OpsModel) async {
        let mine = generation
        let result = await ops.sendWithMeta(AdminAPI.drivers(staleGPS: presence == .stale, limit: 200))
        guard mine == generation else { return }
        if case .failure(let error) = result, error == .cancelled { return }
        if case .success(let page) = result { total = page.meta.total }
        state = LoadState(result.map(\.items), keeping: state)
    }

    /// The server's list changes with "without a fix": start again.
    func reloadFromScratch(_ ops: OpsModel) async {
        generation += 1
        state = .loading
        await load(ops)
    }

    /// Every 20 s while "without a fix" is shown, every minute otherwise.
    func tick(_ ops: OpsModel) async {
        ticks += 1
        guard case .loaded = state else { return }
        if presence == .stale || ticks % 3 == 0 { await load(ops) }
    }

    /// "PRW-1234", "prw 1234" and "PRW1234" are the same plate.
    static func plateKey(_ text: String) -> String {
        Numerals.latin(text).uppercased().filter { $0.isLetter || $0.isNumber }
    }
}

// MARK: - A row

private struct OpDriverRowView: View {
    @Environment(\.strings) private var strings
    let driver: AdminDriver
    let flagStale: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            HStack(spacing: Spacing.s2) {
                Text(OpText.name(driver.fullName, strings))
                    .opsFont(.heading, weight: .medium)
                    .foregroundStyle(Palette.text)
                    .lineLimit(1)
                Spacer(minLength: 0)
                StatusChip(driver: driver.approvalStatus)
                StatusChip(availability: driver.availability)
            }
            HStack(spacing: Spacing.s2) {
                if let phone = driver.phone { LTRText(phone) } else { Text("—") }
                DotSeparator().accessibilityHidden(true)
                if let plate = driver.plateNumber {
                    LTRText(plate)
                    if let status = driver.vehicleStatus, status != .active {
                        Text(OpText.word(status.messageKey, raw: status.rawValue, strings))
                            .foregroundStyle(Palette.attention)
                    }
                } else {
                    Text("—")
                }
            }
            .opsFont(.body)
            .foregroundStyle(Palette.textMuted)
            HStack(spacing: Spacing.s2) {
                Label(OpsFormat.age(seconds: driver.locationAgeSeconds, strings), systemImage: "location")
                    .foregroundStyle(flagStale ? Palette.attention : Palette.textMuted)
                    .accessibilityLabel(strings["admin.col.last_seen"] + " " + OpsFormat.age(seconds: driver.locationAgeSeconds, strings))
                DotSeparator().accessibilityHidden(true)
                Text(OpText.rating(driver.ratingAverage, count: driver.ratingCount, strings))
                DotSeparator().accessibilityHidden(true)
                Text(strings["ride.offers.trips", ["count": driver.completedTrips]])
            }
            .opsFont(.caption)
            .foregroundStyle(Palette.textMuted)
        }
        .padding(.vertical, Spacing.s1)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("drivers.row." + (driver.phone ?? driver.id))
    }
}
