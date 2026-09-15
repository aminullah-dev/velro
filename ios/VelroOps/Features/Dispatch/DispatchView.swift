import Observation
import SwiftUI
import VelroCore

/// Dispatch: trips needing a driver, soonest first (the panel's Dispatch.tsx,
/// section 89).
///
/// Everything a dispatcher needs in the ten seconds each row gets: how long
/// until it leaves, where from and to, how many are on it, whether drivers
/// were already asked and are still deciding, and whether anybody is online
/// to ask at all. At-risk rows are tinted and say so in words. Refreshes every
/// half minute, as the panel does.
///
/// Other screens open it with `navigator.open(.dispatch, filter:)`:
/// "at_risk" (only the departures at risk) or "unassigned" (the whole board).
struct DispatchView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @State private var model = OpDispatchModel()
    @State private var selectedID: String?
    @State private var confirm: ConfirmRequest?

    init() {}

    var body: some View {
        OpSplitReader { isSplit in
            if isSplit {
                OpSplitLayout(listWidth: 440) {
                    board(isSplit: true)
                } detail: {
                    if let trip = model.trip(selectedID) {
                        OpDispatchTripDetail(trip: trip, model: model, offer: { ask(offer: $0) })
                            .id(trip.id)
                    } else {
                        OpNothingSelected(messageKey: "admin.section.unassigned", systemImage: "arrow.triangle.branch")
                    }
                }
            } else {
                board(isSplit: false)
                    .navigationDestination(for: UnassignedTrip.self) { trip in
                        OpDispatchTripDetail(trip: model.trip(trip.id) ?? trip, model: model, offer: { ask(offer: $0) })
                    }
            }
        }
        .background(Palette.background)
        .navigationTitle(strings["admin.nav.operations"])
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Menu {
                    Picker(strings["ops.dispatch.window", ["hours": model.withinHours]], selection: windowBinding) {
                        ForEach(OpDispatchModel.windows, id: \.self) { hours in
                            Text(strings["ops.dispatch.window", ["hours": hours]]).tag(hours)
                        }
                    }
                    .pickerStyle(.inline)
                } label: {
                    Label(strings["ops.dispatch.window", ["hours": model.withinHours]], systemImage: "clock")
                }
                OpRefreshButton { [model, ops] in await model.load(ops) }
            }
        }
        .task { [model, ops] in model.apply(deepLink: ops.navigator.takeFilter(for: .dispatch)) }
        .poll(every: .seconds(30)) { [model, ops] in await model.load(ops) }
        .confirmAction($confirm)
    }

    private var windowBinding: Binding<Int> {
        Binding(get: { model.withinHours }, set: { hours in
            Task { [model, ops] in await model.setWindow(hours, ops) }
        })
    }

    @ViewBuilder
    private func board(isSplit: Bool) -> some View {
        switch model.state {
        case .loading:
            LoadingView()
        case .failed(let error):
            ErrorView(error: error) { [model, ops] in await model.load(ops) }
        case .loaded(let page):
            List(selection: isSplit ? $selectedID : .constant(nil)) {
                Section {
                    OpDispatchHeader(page: page)
                        .listRowSeparator(.hidden)
                        .listRowBackground(Color.clear)
                    if let outcome = model.outcome {
                        Banner(outcome.message(strings), tone: outcome.isError ? .error : .info,
                               systemImage: outcome.isError ? "exclamationmark.triangle" : "paperplane")
                            .listRowSeparator(.hidden)
                            .listRowBackground(Color.clear)
                    }
                }
                let atRisk = page.items.filter(\.atRisk)
                let rows = model.onlyAtRisk ? atRisk : page.items
                if !page.items.isEmpty {
                    OpChipBar(options: [
                        .init(value: false, label: strings["admin.filter.all"], count: page.items.count),
                        .init(value: true, label: strings["admin.dispatch.at_risk"], count: atRisk.count),
                    ], selection: Binding(get: { model.onlyAtRisk }, set: { model.onlyAtRisk = $0 }))
                    .padding(.horizontal, -Spacing.s4)
                    .listRowSeparator(.hidden)
                    .listRowBackground(Color.clear)
                }
                if rows.isEmpty {
                    EmptyStateView(messageKey: page.items.isEmpty ? "admin.empty.unassigned" : "ops.dispatch.none_at_risk",
                                   systemImage: "checkmark.circle")
                        .listRowSeparator(.hidden)
                        .listRowBackground(Color.clear)
                } else {
                    Section {
                        ForEach(rows) { trip in
                            row(trip, isSplit: isSplit)
                        }
                    }
                }
            }
            .listStyle(.plain)
            // Selected beside its detail: a light ground the row's own ink reads on.
            .tint(isSplit ? Palette.bannerInfo : Palette.accent)
            .scrollContentBackground(.hidden)
        }
    }

    @ViewBuilder
    private func row(_ trip: UnassignedTrip, isSplit: Bool) -> some View {
        let content = OpDispatchRow(trip: trip, isOffering: model.offering.contains(trip.id)) { ask(offer: trip) }
        Group {
            if isSplit {
                content.tag(trip.id)
            } else {
                NavigationLink(value: trip) { content }
            }
        }
        .opAttentionRow(trip.atRisk)
    }

    /// Offering rings every driver who could take it: asked first.
    private func ask(offer trip: UnassignedTrip) {
        let again = trip.openOffers > 0
        confirm = ConfirmRequest(
            title: strings[again ? "admin.action.offer_again" : "admin.action.offer"],
            message: strings["ops.dispatch.offer_confirm", [
                // A trip number is Latin inside Dari or Pashto: one run, never reordered.
                "number": "\u{2066}\(trip.number)\u{2069}", "count": trip.candidates,
            ]],
            confirmTitle: strings[again ? "admin.action.offer_again" : "admin.action.offer"]
        ) { [model, ops] _ in
            await model.offer(trip, ops)
        }
    }
}

// MARK: - The model

@MainActor
@Observable
final class OpDispatchModel {
    static let windows = [3, 6, 12, 24, 72]

    private(set) var withinHours = 12
    private(set) var state: LoadState<Paged<[UnassignedTrip]>> = .loading
    /// What the last offer did, for the banner above the board.
    private(set) var outcome: Outcome?
    private(set) var offering: Set<String> = []
    /// Only the departures leaving within the at-risk window with nobody to
    /// drive them: the dashboard's "at risk" card opens the board so.
    var onlyAtRisk = false
    private var generation = 0

    func apply(deepLink: String?) {
        if deepLink == "at_risk" { onlyAtRisk = true }
    }

    enum Outcome {
        case offered(number: String, count: Int)
        case alreadyOffered(number: String)
        case failed(APIError)

        var isError: Bool { if case .failed = self { true } else { false } }

        func message(_ strings: Strings) -> String {
            switch self {
            case .offered(let number, let count):
                "\u{2066}\(number)\u{2069}" + OpsJoin.separator(strings) + strings["admin.dispatch.offered", ["count": count]]
            case .alreadyOffered(let number):
                "\u{2066}\(number)\u{2069}" + OpsJoin.separator(strings) + strings["admin.dispatch.already_offered"]
            case .failed(let error):
                OpText.error(error, strings)
            }
        }
    }

    func trip(_ id: String?) -> UnassignedTrip? {
        guard let id else { return nil }
        return state.value?.items.first { $0.id == id }
    }

    func load(_ ops: OpsModel) async {
        let mine = generation
        let result = await ops.sendWithMeta(AdminAPI.unassigned(withinHours: withinHours))
        guard mine == generation else { return }
        if case .failure(let error) = result, error == .cancelled { return }
        state = LoadState(result, keeping: state)
    }

    /// Which banner is showing, so an old timer does not clear a newer one.
    @ObservationIgnored private var outcomeToken = 0

    /// The banner says what the last offer did, then goes: after a while,
    /// or as soon as the board shows another window.
    private func show(_ new: Outcome) {
        outcome = new
        outcomeToken += 1
        let token = outcomeToken
        Task { @MainActor [weak self] in
            try? await Task.sleep(for: .seconds(30))
            if self?.outcomeToken == token { self?.outcome = nil }
        }
    }

    func setWindow(_ hours: Int, _ ops: OpsModel) async {
        guard hours != withinHours else { return }
        outcome = nil
        withinHours = hours
        generation += 1
        state = .loading
        await load(ops)
    }

    /// Nil closes the confirmation; an error stays in it to read.
    func offer(_ trip: UnassignedTrip, _ ops: OpsModel) async -> APIError? {
        guard !offering.contains(trip.id) else { return nil }
        offering.insert(trip.id)
        defer { offering.remove(trip.id) }
        switch await ops.send(AdminAPI.offerTrip(trip.id)) {
        case .success(let result):
            show(result.offersMade > 0
                ? .offered(number: trip.number, count: result.offersMade)
                : .alreadyOffered(number: trip.number))
            await load(ops)
            await ops.refreshAttention()
            return nil
        case .failure(let error):
            return error
        }
    }
}

// MARK: - The header

private struct OpDispatchHeader: View {
    @Environment(\.strings) private var strings
    let page: Paged<[UnassignedTrip]>

    var body: some View {
        let count = page.meta.count ?? page.items.count
        let atRisk = page.meta.atRisk ?? page.items.filter(\.atRisk).count
        let drivers = page.meta.driversAvailable ?? 0
        VStack(alignment: .leading, spacing: Spacing.s3) {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 170), spacing: Spacing.s3)], spacing: Spacing.s3) {
                StatCard("admin.stat.unassigned", count: count, systemImage: "car.2", attention: true)
                StatCard("admin.stat.departures_at_risk", count: atRisk, noteKey: "admin.stat.at_risk_hint",
                         systemImage: "exclamationmark.triangle", attention: true)
                StatCard("admin.stat.drivers_online", count: drivers, systemImage: "steeringwheel")
            }
            if count > 0 {
                Text(strings["admin.dispatch.summary", ["at_risk": atRisk, "drivers": drivers]])
                    .opsFont(.label, weight: .regular)
                    .foregroundStyle(Palette.textMuted)
            }
        }
        .padding(.vertical, Spacing.s2)
    }
}

// MARK: - A row

private struct OpDispatchRow: View {
    @Environment(\.strings) private var strings
    let trip: UnassignedTrip
    let isOffering: Bool
    let offer: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: Spacing.s3) {
            VStack(alignment: .leading, spacing: Spacing.s1) {
                HStack(spacing: Spacing.s2) {
                    Text(OpText.untilDeparture(minutes: trip.minutesToDeparture, strings))
                        .opsFont(.heading, weight: .bold)
                        .foregroundStyle(trip.atRisk ? Palette.attention : Palette.text)
                    if trip.atRisk {
                        StatusChip(strings["admin.dispatch.at_risk"], tone: .attention)
                    }
                    Spacer(minLength: 0)
                    LTRText(trip.number)
                        .opsFont(.caption)
                        .foregroundStyle(Palette.textMuted)
                }
                Text(OpText.route(trip.originStationName, trip.destinationName, strings))
                    .opsFont(.body)
                    .foregroundStyle(Palette.text)
                    .lineLimit(2)
                HStack(spacing: Spacing.s3) {
                    DateText(trip.scheduledDepartureAt)
                    Label(OpText.seats(booked: trip.bookedSeats, capacity: trip.seatCapacity, strings),
                          systemImage: "person.fill")
                        .labelStyle(.titleAndIcon)
                        .accessibilityLabel(strings["admin.col.seats"] + " "
                                            + OpText.seats(booked: trip.bookedSeats, capacity: trip.seatCapacity, strings))
                }
                .opsFont(.caption)
                .foregroundStyle(Palette.textMuted)
                OpDispatchOffersLine(trip: trip)
            }
            VStack {
                Button(action: offer) {
                    if isOffering {
                        ProgressView().controlSize(.small)
                    } else {
                        Text(strings[trip.openOffers > 0 ? "admin.action.offer_again" : "admin.action.offer"])
                    }
                }
                .buttonStyle(.borderless)
                .opsFont(.label, weight: .medium)
                .foregroundStyle(trip.candidates == 0 ? Palette.textMuted : Palette.accent)
                .disabled(isOffering || trip.candidates == 0)
                // A disabled button with no reason is a broken button.
                .help(trip.candidates == 0 ? strings["admin.dispatch.nobody_online"] : "")
            }
        }
        .padding(.vertical, Spacing.s1)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("dispatch.row." + trip.number)
        .accessibilityAction(named: strings[trip.openOffers > 0 ? "admin.action.offer_again" : "admin.action.offer"]) {
            if trip.candidates > 0, !isOffering { offer() }
        }
    }
}

/// "3 waiting for an answer · expire in 4 min", "Nobody asked yet", and who
/// is online to ask.
private struct OpDispatchOffersLine: View {
    @Environment(\.strings) private var strings
    let trip: UnassignedTrip

    var body: some View {
        HStack(spacing: Spacing.s2) {
            if trip.openOffers == 0 {
                Text(strings["admin.dispatch.no_offers"])
                    .foregroundStyle(Palette.textMuted)
            } else {
                Image(systemName: "paperplane.fill")
                    .foregroundStyle(Palette.accent)
                    .accessibilityHidden(true)
                Text(strings["admin.dispatch.offers_open", ["count": trip.openOffers]])
                    .foregroundStyle(Palette.text)
                if let minutes = trip.offersExpireInMinutes {
                    Text(strings["admin.dispatch.expires_in", ["minutes": minutes]])
                        .foregroundStyle(Palette.textMuted)
                }
            }
            DotSeparator().foregroundStyle(Palette.textMuted).accessibilityHidden(true)
            if trip.candidates > 0 {
                Text(strings["admin.dispatch.candidates", ["count": trip.candidates]])
                    .foregroundStyle(Palette.text)
            } else {
                Text(strings["admin.dispatch.nobody_online"])
                    .foregroundStyle(Palette.attention)
            }
        }
        .opsFont(.caption)
        .lineLimit(2)
    }
}

// MARK: - The detail

/// One trip that needs a driver: the board's row in full, the offer button,
/// and who is already booked on it.
struct OpDispatchTripDetail: View {
    @Environment(\.strings) private var strings
    let trip: UnassignedTrip
    let model: OpDispatchModel
    let offer: (UnassignedTrip) -> Void

    var body: some View {
        Form {
            Section {
                OpDetailTitle(trip.number, subtitle: OpText.route(trip.originStationName, trip.destinationName, strings),
                              isLatin: true) {
                    StatusChip(trip: trip.status)
                    StatusChip(OpText.rideKind(trip.rideKind, strings))
                    if trip.atRisk { StatusChip(strings["admin.dispatch.at_risk"], tone: .attention) }
                }
                .padding(.vertical, Spacing.s2)
            }
            Section {
                OpField("admin.col.departure") {
                    VStack(alignment: .trailing, spacing: 2) {
                        DateText(trip.scheduledDepartureAt)
                        Text(OpText.untilDeparture(minutes: trip.minutesToDeparture, strings))
                            .opsFont(.caption)
                            .foregroundStyle(trip.atRisk ? Palette.attention : Palette.textMuted)
                    }
                }
                OpField("admin.col.origin", text: trip.originStationName ?? "—")
                OpField("admin.col.destination", text: trip.destinationName ?? "—")
                OpField("admin.col.seats", text: OpText.seats(booked: trip.bookedSeats, capacity: trip.seatCapacity, strings))
                OpField("admin.col.offers") {
                    if trip.openOffers == 0 {
                        Text(strings["admin.dispatch.no_offers"])
                    } else {
                        VStack(alignment: .trailing, spacing: 2) {
                            Text(strings["admin.dispatch.offers_open", ["count": trip.openOffers]])
                            if let minutes = trip.offersExpireInMinutes {
                                Text(strings["admin.dispatch.expires_in", ["minutes": minutes]])
                                    .opsFont(.caption)
                                    .foregroundStyle(Palette.textMuted)
                            }
                        }
                    }
                }
                OpField("admin.col.available") {
                    Text(trip.candidates > 0
                         ? strings["admin.dispatch.candidates", ["count": trip.candidates]]
                         : strings["admin.dispatch.nobody_online"])
                        .foregroundStyle(trip.candidates > 0 ? Palette.text : Palette.attention)
                }
            }
            Section {
                let busy = model.offering.contains(trip.id)
                Button {
                    offer(trip)
                } label: {
                    HStack {
                        Spacer()
                        if busy {
                            ProgressView().controlSize(.small)
                        } else {
                            Label(strings[trip.openOffers > 0 ? "admin.action.offer_again" : "admin.action.offer"],
                                  systemImage: "paperplane")
                                .opsFont(.body, weight: .medium)
                                // The accent is mint in dark mode: white on it does not read.
                                .foregroundStyle(Palette.onAccent)
                        }
                        Spacer()
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(busy || trip.candidates == 0)
                .keyboardShortcut("o", modifiers: .command)
                .accessibilityIdentifier("dispatch.offer")
                .listRowBackground(Color.clear)
                if trip.candidates == 0 {
                    Text(strings["admin.dispatch.nobody_online"])
                        .opsFont(.caption)
                        .foregroundStyle(Palette.textMuted)
                        .listRowBackground(Color.clear)
                }
            }
            OpTripBookingsSection(tripId: trip.id)
        }
        .formStyle(.grouped)
        .scrollContentBackground(.hidden)
        .background(Palette.background)
        .opNavigationTitle(trip.number)
    }
}
