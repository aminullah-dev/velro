import Observation
import SwiftUI
import VelroCore

/// Trips: the live board and the archive behind it (the panel's Trips.tsx,
/// section 53), filterable by the same slices the dashboard's cards count
/// with, scrolling on into older pages as the reader reaches the end.
///
/// Other screens open it on a slice with `navigator.open(.trips, filter:)`:
/// "overdue", "active", "unassigned", "departing:<hours>" (or "departing" for
/// two hours), "all", "status:<TRIP_STATUS>", or "trip:<number>" (the live
/// map's driver panel: the trip is looked for among active trips, then among
/// the newest, and selected -- pushed on an iPhone).
struct TripsView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @State private var model = OpTripsModel()
    @State private var selectedID: String?
    /// A trip another screen asked for, pushed on an iPhone.
    @State private var pushed: AdminTrip?

    init() {}

    var body: some View {
        OpSplitReader { isSplit in
            if isSplit {
                OpSplitLayout(listWidth: 420) {
                    list(isSplit: true)
                } detail: {
                    if let trip = model.pager.items.first(where: { $0.id == selectedID }) {
                        OpTripDetailView(trip: trip).id(trip.id)
                    } else {
                        OpNothingSelected(messageKey: "ops.trips.choose", systemImage: "car.2")
                    }
                }
            } else {
                list(isSplit: false)
                    .navigationDestination(for: AdminTrip.self) { trip in
                        OpTripDetailView(trip: trip)
                    }
                    .navigationDestination(item: $pushed) { trip in
                        OpTripDetailView(trip: trip)
                    }
            }
        }
        .background(Palette.background)
        .navigationTitle(strings["admin.nav.trips"])
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                filterMenu
                OpRefreshButton { [model] in await model.pager.refresh() }
            }
        }
        .task { [model, ops] in
            model.apply(deepLink: ops.navigator.takeFilter(for: .trips))
            if let found = await model.reloadFindingPending(ops) {
                selectedID = found.id
                pushed = found
            }
        }
        // The live slices move; the archive does not (Trips.tsx).
        .poll(every: .seconds(20)) { [model] in
            if model.isLive { await model.pager.refresh() }
        }
    }

    private var filterMenu: some View {
        Menu {
            Picker(strings["admin.col.status"], selection: statusBinding) {
                Text(strings["admin.filter.all"]).tag(TripStatus?.none)
                ForEach(TripStatus.allCases, id: \.self) { status in
                    Text(OpText.word(status.messageKey, raw: status.rawValue, strings)).tag(TripStatus?.some(status))
                }
            }
            .pickerStyle(.menu)
            Picker(strings["admin.col.departure"], selection: hoursBinding) {
                Text(strings["admin.filter.all"]).tag(Int?.none)
                ForEach(OpTripsModel.windows, id: \.self) { hours in
                    Text(strings["ops.trips.departing_within", ["hours": hours]]).tag(Int?.some(hours))
                }
            }
            .pickerStyle(.menu)
        } label: {
            Label(strings["admin.col.status"], systemImage: model.status == nil
                  ? "line.3.horizontal.decrease.circle" : "line.3.horizontal.decrease.circle.fill")
        }
    }

    private var statusBinding: Binding<TripStatus?> {
        Binding(get: { model.status }, set: { value in
            model.status = value
            Task { [model, ops] in await model.reload(ops) }
        })
    }

    private var hoursBinding: Binding<Int?> {
        Binding(get: { model.slice.hours }, set: { value in
            model.slice = value.map { .departing($0) } ?? .all
            Task { [model, ops] in await model.reload(ops) }
        })
    }

    private var sliceBinding: Binding<OpTripsModel.Slice> {
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
            OpChipBar(options: model.sliceOptions(strings), selection: sliceBinding)
            if model.status != nil {
                HStack(spacing: Spacing.s2) {
                    Text(strings["admin.col.status"])
                        .opsFont(.caption)
                        .foregroundStyle(Palette.textMuted)
                    if let status = model.status { StatusChip(trip: status) }
                    Button {
                        statusBinding.wrappedValue = nil
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .accessibilityLabel(strings["admin.filter.all"])
                    }
                    .buttonStyle(.borderless)
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, Spacing.s4)
                .padding(.bottom, Spacing.s2)
            }
            Divider()
            content(isSplit: isSplit)
        }
    }

    @ViewBuilder
    private func content(isSplit: Bool) -> some View {
        let pager = model.pager
        if pager.isFirstLoad {
            LoadingView()
        } else if let error = pager.error {
            ErrorView(error: error) { [model, ops] in await model.reload(ops) }
        } else if pager.items.isEmpty {
            EmptyStateView(messageKey: "admin.empty.trips", systemImage: "car.2")
        } else {
            List(selection: isSplit ? $selectedID : .constant(nil)) {
                ForEach(pager.items) { trip in
                    Group {
                        if isSplit {
                            OpTripRowView(trip: trip).tag(trip.id)
                        } else {
                            NavigationLink(value: trip) { OpTripRowView(trip: trip) }
                        }
                    }
                    .opAttentionRow(OpTripsModel.needsAttention(trip))
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

// MARK: - The model

@MainActor
@Observable
final class OpTripsModel {
    /// Which slice, as the panel's chip row: one at a time.
    enum Slice: Hashable {
        case all, active, unassigned, overdue
        case departing(Int)

        var hours: Int? { if case .departing(let hours) = self { hours } else { nil } }
    }

    static let windows = [2, 3, 6, 12, 24, 72]

    // Any chip the operator picks leaves the one-trip lookup behind.
    var slice: Slice = .all { didSet { onlyNumber = nil } }
    var status: TripStatus? { didSet { onlyNumber = nil } }
    /// One trip by its number, when "trip:<number>" named one older than
    /// the pages of the newest: the list is that trip alone until a chip is
    /// chosen.
    private(set) var onlyNumber: String?
    let pager = OpPager<AdminTrip>(pageSize: 50)
    /// "trip:<number>" from another screen, until it is found or given up on.
    private(set) var pendingNumber: String?

    /// Worth refreshing on a timer: anything but the plain archive.
    var isLive: Bool { slice != .all || status != nil }

    /// The filter another screen left: see `TripsView`.
    func apply(deepLink: String?) {
        guard let deepLink else { return }
        let parts = deepLink.split(separator: ":", maxSplits: 1).map(String.init)
        switch parts.first {
        case "overdue": slice = .overdue
        case "active", "active_only": slice = .active
        case "unassigned", "needs_driver": slice = .unassigned
        case "departing", "soon":
            let hours = parts.count > 1 ? Int(parts[1]) ?? 2 : 2
            slice = .departing(min(72, max(1, hours)))
        case "status":
            if parts.count > 1, let value = TripStatus(rawValue: parts[1].uppercased()) {
                slice = .all
                status = value
            }
        case "all": slice = .all
        case "trip":
            if parts.count > 1, !parts[1].isEmpty {
                pendingNumber = parts[1]
                slice = .active
            }
        default: break
        }
    }

    func sliceOptions(_ strings: Strings) -> [OpChipBar<Slice>.Option] {
        var options: [OpChipBar<Slice>.Option] = [
            .init(value: .all, label: onlyNumber.map { "\u{2066}\($0)\u{2069}" } ?? strings["admin.filter.all"]),
            .init(value: .active, label: strings["admin.filter.active_only"]),
            .init(value: .unassigned, label: strings["admin.filter.needs_driver"]),
            .init(value: .overdue, label: strings["admin.filter.overdue"]),
            .init(value: .departing(2), label: strings["admin.filter.departing_soon"]),
        ]
        // A card may ask for a window the chip row does not offer (24 h for
        // "nearly full"): it gets a chip of its own while it is chosen.
        if let hours = slice.hours, hours != 2 {
            options.append(.init(value: .departing(hours), label: strings["ops.trips.departing_within", ["hours": hours]]))
        }
        return options
    }

    /// The first page -- and the trip another screen asked for: among the
    /// active ones first, then among the newest of all, then by its number
    /// from the server. Nil only when there is no such trip.
    func reloadFindingPending(_ ops: OpsModel) async -> AdminTrip? {
        await reload(ops)
        guard let number = pendingNumber else { return nil }
        pendingNumber = nil
        if let found = pager.items.first(where: { $0.number == number }) { return found }
        if slice != .all || status != nil {
            slice = .all
            status = nil
            await reload(ops)
            if let found = pager.items.first(where: { $0.number == number }) { return found }
        }
        // Older than a page of the newest: the server finds that one trip.
        onlyNumber = number
        await reload(ops)
        return pager.items.first { $0.number == number }
    }

    func reload(_ ops: OpsModel) async {
        let filter = filter
        await pager.reload { [ops] limit, offset in
            var page = filter
            page.limit = limit
            page.offset = offset
            return await ops.sendWithMeta(AdminAPI.trips(page))
        }
    }

    private var filter: TripFilter {
        var filter = TripFilter(status: status)
        filter.number = onlyNumber
        switch slice {
        case .all: break
        case .active: filter.activeOnly = true
        case .unassigned: filter.unassigned = true
        case .overdue: filter.overdue = true
        case .departing(let hours): filter.departingWithinHours = hours
        }
        return filter
    }

    /// A trip nobody is driving that leaves within the hour or left within
    /// the last one -- the dispatch board's own window. Older ones are a
    /// record, not a job: tinting a week of overdue rows says nothing.
    static func needsAttention(_ trip: AdminTrip, now: Date = .now) -> Bool {
        guard !trip.hasDriver, [.scheduled, .requested].contains(trip.status), let departure = trip.departure else {
            return false
        }
        return abs(departure.timeIntervalSince(now)) < 3600
    }
}

// MARK: - A row

struct OpTripRowView: View {
    @Environment(\.strings) private var strings
    let trip: AdminTrip

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            HStack(spacing: Spacing.s2) {
                LTRText(trip.number)
                    .opsFont(.label, weight: .medium)
                    .foregroundStyle(Palette.text)
                StatusChip(trip: trip.status)
                Spacer(minLength: 0)
                Label(OpText.seats(booked: trip.bookedSeats, capacity: trip.seatCapacity, strings), systemImage: "person.fill")
                    .labelStyle(.titleAndIcon)
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
                    .accessibilityLabel(strings["admin.col.seats"] + " "
                                        + OpText.seats(booked: trip.bookedSeats, capacity: trip.seatCapacity, strings))
            }
            Text(OpText.route(trip.originStationName, trip.destinationName, strings))
                .opsFont(.body)
                .foregroundStyle(Palette.text)
                .lineLimit(2)
            HStack(spacing: Spacing.s2) {
                DateText(trip.scheduledDepartureAt)
                DotSeparator().accessibilityHidden(true)
                if trip.hasDriver {
                    Text(OpText.name(trip.driverName, strings))
                        .lineLimit(1)
                    if let plate = trip.plateNumber {
                        LTRText(plate)
                    }
                } else {
                    Text(strings["admin.filter.needs_driver"])
                        .foregroundStyle(Palette.attention)
                }
            }
            .opsFont(.caption)
            .foregroundStyle(Palette.textMuted)
        }
        .padding(.vertical, Spacing.s1)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("trips.row." + trip.number)
    }
}
