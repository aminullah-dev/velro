import Observation
import SwiftUI
import VelroCore

/// Live requests: passengers waiting for a driver to name a price, and what
/// they have been offered (the panel's Negotiations.tsx, section 89).
///
/// Read only, deliberately: the fare is between the passenger and the driver.
/// What the office needs is to see whether anyone has answered somebody who
/// rings to say nobody will take them -- so an unanswered request is tinted
/// and says so in words. Refreshes every fifteen seconds, as the panel does.
///
/// Other screens open it with `navigator.open(.liveRequests, filter:
/// "unanswered")`: only the requests nobody has answered.
struct LiveRequestsView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @State private var model = OpLiveRequestsModel()
    @State private var selectedID: String?

    init() {}

    var body: some View {
        OpSplitReader { isSplit in
            if isSplit {
                OpSplitLayout(listWidth: 440) {
                    list(isSplit: true)
                } detail: {
                    if let request = model.request(selectedID) {
                        OpRideRequestDetail(request: request).id(request.id)
                    } else {
                        OpNothingSelected(messageKey: "ops.requests.choose", systemImage: "hand.raised")
                    }
                }
            } else {
                list(isSplit: false)
                    .navigationDestination(for: AdminRideRequest.self) { request in
                        OpRideRequestDetail(request: model.request(request.id) ?? request)
                    }
            }
        }
        .background(Palette.background)
        .navigationTitle(strings["admin.nav.negotiations"])
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                OpRefreshButton { [model, ops] in await model.load(ops) }
            }
        }
        .task { [model, ops] in
            if ops.navigator.takeFilter(for: .liveRequests) == "unanswered" { model.onlyUnanswered = true }
        }
        .poll(every: .seconds(15)) { [model, ops] in await model.load(ops) }
    }

    @ViewBuilder
    private func list(isSplit: Bool) -> some View {
        switch model.state {
        case .loading:
            LoadingView()
        case .failed(let error):
            ErrorView(error: error) { [model, ops] in await model.load(ops) }
        case .loaded(let requests):
            let shown = model.onlyUnanswered ? requests.filter(\.isUnanswered) : requests
            List(selection: isSplit ? $selectedID : .constant(nil)) {
                Section {
                    header(requests)
                        .listRowSeparator(.hidden)
                        .listRowBackground(Color.clear)
                }
                if shown.isEmpty {
                    EmptyStateView(messageKey: "admin.negotiations.none", systemImage: "hand.raised")
                        .listRowSeparator(.hidden)
                        .listRowBackground(Color.clear)
                } else {
                    Section {
                        ForEach(shown) { request in
                            Group {
                                if isSplit {
                                    OpRideRequestRow(request: request).tag(request.id)
                                } else {
                                    NavigationLink(value: request) { OpRideRequestRow(request: request) }
                                }
                            }
                            .opAttentionRow(request.isUnanswered)
                        }
                    }
                }
            }
            .listStyle(.plain)
            // Selected beside its detail: a light ground the row's own ink reads on.
            .tint(isSplit ? Palette.bannerInfo : Palette.accent)
            .scrollContentBackground(.hidden)
            .refreshable { [model, ops] in await model.load(ops) }
        }
    }

    private func header(_ requests: [AdminRideRequest]) -> some View {
        let unanswered = requests.filter(\.isUnanswered).count
        return VStack(alignment: .leading, spacing: Spacing.s3) {
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 170), spacing: Spacing.s3)], spacing: Spacing.s3) {
                StatCard("admin.stat.open_requests", count: requests.count, systemImage: "hand.raised")
                StatCard("admin.stat.unanswered_requests", count: unanswered, systemImage: "exclamationmark.bubble",
                         attention: true)
            }
            Banner(strings["admin.negotiations.readonly"], tone: .info, systemImage: "lock")
            OpChipBar(options: [
                .init(value: false, label: strings["admin.filter.all"], count: requests.count),
                .init(value: true, label: strings["admin.negotiations.no_offers"], count: unanswered),
            ], selection: Binding(get: { model.onlyUnanswered }, set: { model.onlyUnanswered = $0 }))
            .padding(.horizontal, -Spacing.s4)
        }
        .padding(.vertical, Spacing.s2)
    }
}

// MARK: - The model

@MainActor
@Observable
final class OpLiveRequestsModel {
    private(set) var state: LoadState<[AdminRideRequest]> = .loading
    var onlyUnanswered = false

    func request(_ id: String?) -> AdminRideRequest? {
        guard let id else { return nil }
        return state.value?.first { $0.id == id }
    }

    func load(_ ops: OpsModel) async {
        let result = await ops.send(AdminAPI.rideRequests(limit: 100))
        if case .failure(let error) = result, error == .cancelled { return }
        state = LoadState(result, keeping: state)
    }
}

// MARK: - A row

private struct OpRideRequestRow: View {
    @Environment(\.strings) private var strings
    let request: AdminRideRequest

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            HStack(spacing: Spacing.s2) {
                Text(OpText.name(request.passengerName, strings))
                    .opsFont(.heading, weight: .medium)
                    .foregroundStyle(Palette.text)
                    .lineLimit(1)
                if request.isUnanswered {
                    StatusChip(strings["admin.negotiations.no_offers"], tone: .attention)
                }
                Spacer(minLength: 0)
                MoneyText(request.offeredFare)
                    .opsFont(.label, weight: .medium)
                    .foregroundStyle(Palette.text)
                    .accessibilityLabel(strings["admin.negotiations.asking"] + " "
                                        + OpsFormat.money(request.offeredFare, strings: strings))
            }
            Text(OpText.route(request.originStationName, request.destinationName, strings))
                .opsFont(.body)
                .foregroundStyle(Palette.text)
                .lineLimit(2)
            HStack(spacing: Spacing.s2) {
                Label(OpsFormat.count(request.passengerCount, strings), systemImage: "person.2.fill")
                    .accessibilityLabel(strings["driver.label.passengers"] + " " + OpsFormat.count(request.passengerCount, strings))
                DotSeparator().accessibilityHidden(true)
                DateText(request.requestedFor)
                DotSeparator().accessibilityHidden(true)
                DateText(request.createdAt, style: .relative)
            }
            .opsFont(.caption)
            .foregroundStyle(Palette.textMuted)
            if !request.offers.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    ForEach(request.offers.prefix(3)) { offer in
                        OpOfferLine(offer: offer)
                    }
                    if request.offers.count > 3 {
                        Text("+" + OpsFormat.count(request.offers.count - 3, strings))
                            .opsFont(.caption)
                            .foregroundStyle(Palette.textMuted)
                    }
                }
                .padding(.top, 2)
            }
        }
        .padding(.vertical, Spacing.s1)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("requests.row." + (request.passengerPhone ?? request.id))
    }
}

/// "1,800 AFN · Mohammad · PRW-1234".
private struct OpOfferLine: View {
    @Environment(\.strings) private var strings
    let offer: AdminRideRequest.Offer

    var body: some View {
        HStack(spacing: Spacing.s1) {
            Image(systemName: "tag.fill")
                .foregroundStyle(Palette.accent)
                .accessibilityHidden(true)
            MoneyText(offer.amount)
                .foregroundStyle(Palette.text)
            if let name = offer.driverName {
                Text("· " + name).lineLimit(1)
            }
            if let plate = offer.vehiclePlate {
                DotSeparator().accessibilityHidden(true)
                LTRText(plate)
            }
        }
        .opsFont(.caption)
        .foregroundStyle(Palette.textMuted)
    }
}

// MARK: - The detail

private struct OpRideRequestDetail: View {
    @Environment(\.strings) private var strings
    let request: AdminRideRequest

    var body: some View {
        Form {
            Section {
                OpDetailTitle(OpText.name(request.passengerName, strings),
                              subtitle: OpText.route(request.originStationName, request.destinationName, strings)) {
                    if request.isUnanswered {
                        StatusChip(strings["admin.negotiations.no_offers"], tone: .attention)
                    } else {
                        StatusChip(strings["home.open_request.offers", ["count": request.offerCount]], tone: .active)
                    }
                }
                .padding(.vertical, Spacing.s2)
            }
            Section {
                OpField("admin.col.phone") { PhoneLink(request.passengerPhone) }
                OpField("admin.negotiations.asking") { MoneyText(request.offeredFare) }
                if let back = request.returnFare {
                    OpField("ride.ask.fare_back") { MoneyText(back) }
                }
                OpField("driver.label.passengers", text: OpsFormat.count(request.passengerCount, strings))
                OpField("ride.when.departure") { DateText(request.requestedFor) }
                if let returnFor = request.returnFor {
                    OpField("ride.return.label") { DateText(returnFor) }
                }
                OpField("admin.col.waiting") {
                    VStack(alignment: .trailing, spacing: 2) {
                        DateText(request.createdAt)
                        DateText(request.createdAt, style: .relative)
                            .opsFont(.caption)
                            .foregroundStyle(Palette.textMuted)
                    }
                }
                OpField("admin.col.expires") {
                    TimelineView(.periodic(from: .now, by: 30)) { context in
                        Text(expiry(now: context.date))
                    }
                }
                if let note = request.note, !note.isEmpty {
                    OpField("ride.ask.note", text: note)
                }
            }
            Section {
                if request.offers.isEmpty {
                    Text(strings["ops.requests.no_offers"])
                        .opsFont(.body)
                        .foregroundStyle(Palette.attention)
                } else {
                    ForEach(request.offers) { offer in
                        OpOfferDetail(offer: offer)
                    }
                }
            } header: {
                OpFormHeader(titleKey: "admin.negotiations.offers")
            } footer: {
                Text(strings["admin.negotiations.readonly"])
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
            }
        }
        .formStyle(.grouped)
        .scrollContentBackground(.hidden)
        .background(Palette.background)
        .opNavigationTitle(OpText.name(request.passengerName, strings))
    }

    private func expiry(now: Date) -> String {
        guard let expires = request.expires else { return "—" }
        let minutes = Calendars.minutesUntil(expires, now: now)
        if minutes < 1 { return strings["home.open_request.expiring"] }
        return strings["home.open_request.expires_in", ["minutes": minutes]]
    }
}

private struct OpOfferDetail: View {
    @Environment(\.strings) private var strings
    let offer: AdminRideRequest.Offer

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            HStack(spacing: Spacing.s2) {
                Text(OpText.name(offer.driverName, strings))
                    .opsFont(.body, weight: .medium)
                Spacer(minLength: 0)
                MoneyText(offer.amount)
                    .opsFont(.body, weight: .medium)
            }
            if let back = offer.returnAmount {
                HStack(spacing: Spacing.s1) {
                    Text(strings["ride.offers.leg_back"])
                    MoneyText(back)
                }
                .opsFont(.caption)
                .foregroundStyle(Palette.textMuted)
            }
            HStack(spacing: Spacing.s2) {
                Text(OpText.stars(offer.driverRating, strings))
                if let trips = offer.driverTrips {
                    DotSeparator().accessibilityHidden(true)
                    Text(strings["ride.offers.trips", ["count": trips]])
                }
                if let plate = offer.vehiclePlate {
                    DotSeparator().accessibilityHidden(true)
                    LTRText(plate)
                }
                if let vehicle = offer.vehicleDescription {
                    DotSeparator().accessibilityHidden(true)
                    Text(vehicle).lineLimit(1)
                }
            }
            .opsFont(.caption)
            .foregroundStyle(Palette.textMuted)
            if let note = offer.note, !note.isEmpty {
                Text(note)
                    .opsFont(.caption)
                    .foregroundStyle(Palette.text)
            }
            if let created = offer.createdAt {
                DateText(created, style: .relative)
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
            }
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
    }
}
