import Observation
import SwiftUI
import VelroCore

/// Every passenger waiting, and the price he has put on each.
@MainActor
@Observable
final class BoardModel {
    private(set) var requests: [RideRequest] = []
    private(set) var myOffers: [FareOffer] = []
    private(set) var isLoading = true
    private(set) var busyRequestId: String?
    private(set) var error: APIError?
    /// The request whose price sheet is open. The poll waits while it is, so
    /// the card he is pricing does not move under his thumb.
    var offeringOn: RideRequest?

    private let app: AppModel

    init(app: AppModel) { self.app = app }

    func myOffer(on requestId: String) -> FareOffer? {
        myOffers.first { $0.rideRequestId == requestId && $0.isOpen }
    }

    func load() async {
        async let board = app.client.send(API.openRideRequests())
        async let mine = app.client.send(API.myFareOffers())
        let (fetched, offers) = await (board, mine)
        switch fetched {
        case .success(let list):
            requests = list
            if case .success(let own) = offers { myOffers = own }
            error = nil
        case .failure(let failure):
            // A failed poll keeps the board he is reading; only an empty screen
            // becomes an error.
            if requests.isEmpty, failure != .cancelled { error = failure }
        }
        isLoading = false
    }

    func poll() async {
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(8))
            if Task.isCancelled { return }
            if offeringOn == nil && busyRequestId == nil { await load() }
        }
    }

    func offer(_ request: RideRequest, amountMinor: Int64, returnAmountMinor: Int64?, note: String?) async {
        busyRequestId = request.id
        error = nil
        let result = await app.client.send(API.offerFare(requestId: request.id, amountMinor: amountMinor, returnAmountMinor: returnAmountMinor, note: note))
        busyRequestId = nil
        switch result {
        case .success:
            offeringOn = nil
            await load()
        case .failure(let failure):
            if failure != .cancelled { error = failure }
        }
    }

    func withdraw(_ offer: FareOffer) async {
        busyRequestId = offer.rideRequestId
        error = nil
        let result = await app.client.send(API.withdrawOffer(offer.id))
        busyRequestId = nil
        if case .failure(let failure) = result, failure != .cancelled { error = failure }
        await load()
    }
}

struct BoardView: View {
    @Environment(\.strings) private var strings
    @State private var model: BoardModel

    init(app: AppModel) {
        _model = State(initialValue: BoardModel(app: app))
    }

    var body: some View {
        VelroScreen(title: strings["driver.board.title"]) {
            Group {
                if model.isLoading {
                    LoadingState()
                } else if let error = model.error, model.requests.isEmpty {
                    ErrorState(error: error) { Task { await model.load() } }
                } else if model.requests.isEmpty {
                    EmptyState(key: "driver.board.empty", systemImage: "person.3")
                } else {
                    ScrollView {
                        LazyVStack(spacing: Spacing.sm) {
                            if let error = model.error, model.offeringOn == nil { InlineError(error: error) }
                            ForEach(model.requests) { request in
                                RequestCard(
                                    request: request,
                                    mine: model.myOffer(on: request.id),
                                    busy: model.busyRequestId == request.id,
                                    offer: { model.offeringOn = request },
                                    withdraw: { offer in Task { await model.withdraw(offer) } }
                                )
                            }
                        }
                        .padding(.horizontal, Spacing.gutter)
                        .padding(.vertical, Spacing.md)
                    }
                    .refreshable { await model.load() }
                }
            }
        }
        .task {
            await model.load()
            await model.poll()
        }
        .sheet(item: $model.offeringOn) { request in
            OfferSheet(model: model, request: request)
                .presentationDetents([.medium, .large])
        }
    }
}

private struct RequestCard: View {
    let request: RideRequest
    let mine: FareOffer?
    let busy: Bool
    let offer: () -> Void
    let withdraw: (FareOffer) -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.xs) {
                Text(strings["ride.journey.from_to", [
                    "origin": request.originStationName ?? strings["common.value.unknown"],
                    "destination": request.destinationName ?? strings["common.value.unknown"],
                ]])
                .velroFont(.heading, weight: .medium)
                .foregroundStyle(Palette.onSurface)
                if let departure = request.departure {
                    Text(strings["ride.when.departure"] + ": " + Calendars.dateTime(departure, strings.locale))
                        .velroFont(.caption)
                        .foregroundStyle(Palette.accent)
                }
                if let back = ISODate.parse(request.returnFor) {
                    Text(strings["ride.return.label"] + ": " + Calendars.dateTime(back, strings.locale))
                        .velroFont(.caption)
                        .foregroundStyle(Palette.accent)
                }
                HStack(alignment: .firstTextBaseline) {
                    Text(strings["ride.ask.passengers"] + " " + Numerals.localise(String(request.passengerCount), strings.locale))
                        .velroFont(.label)
                        .foregroundStyle(Palette.onSurfaceVariant)
                    Spacer()
                    Text(MoneyFormatter.format(request.askingTotal, strings: strings))
                        .velroFont(.headline, weight: .bold)
                        .foregroundStyle(Palette.onSurface)
                }
                if let back = request.returnFare {
                    Text(strings["ride.offers.leg_out"] + " " + MoneyFormatter.format(request.offeredFare, strings: strings)
                         + "  ·  " + strings["ride.offers.leg_back"] + " " + MoneyFormatter.format(back, strings: strings))
                        .velroFont(.caption)
                        .foregroundStyle(Palette.onSurfaceVariant)
                }
                if let note = request.note, !note.isEmpty {
                    Text(note)
                        .velroFont(.label)
                        .foregroundStyle(Palette.onSurfaceVariant)
                }
                if let mine {
                    Text(strings["driver.board.offered", ["amount": MoneyFormatter.format(mine.total, strings: strings)]])
                        .velroFont(.body, weight: .medium)
                        .foregroundStyle(Palette.primary)
                        .padding(.top, Spacing.xs)
                    SecondaryButton(label: strings["driver.board.withdraw"], enabled: !busy) { withdraw(mine) }
                } else {
                    PrimaryButton(label: strings["driver.board.offer"], enabled: !busy, action: offer)
                        .padding(.top, Spacing.xs)
                        .accessibilityIdentifier("board.offer")
                }
            }
        }
    }
}

/// His price: the one they asked for in a tap, or his own.
private struct OfferSheet: View {
    let model: BoardModel
    let request: RideRequest
    @Environment(\.strings) private var strings
    @State private var amount = ""
    @State private var returnAmount = ""
    @State private var note = ""

    private var wantsReturn: Bool { request.returnFare != nil }
    private var minor: Int64? { Int64(amount).map { $0 * 100 } }
    private var returnMinor: Int64? { Int64(returnAmount).map { $0 * 100 } }
    private var ready: Bool {
        guard let minor, minor > 0 else { return false }
        return !wantsReturn || (returnMinor ?? 0) > 0
    }
    private var busy: Bool { model.busyRequestId == request.id }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.md) {
                Text(strings["driver.offer.title"])
                    .velroFont(.title, weight: .bold)
                    .foregroundStyle(Palette.onSurface)
                Text(strings["driver.offer.hint"])
                    .velroFont(.body)
                    .foregroundStyle(Palette.onSurfaceVariant)

                SecondaryButton(
                    label: strings["driver.offer.match", ["amount": MoneyFormatter.format(request.askingTotal, strings: strings)]],
                    enabled: !busy
                ) {
                    Task {
                        await model.offer(request, amountMinor: request.offeredFare.amountMinor,
                                          returnAmountMinor: request.returnFare?.amountMinor, note: note)
                    }
                }
                .accessibilityIdentifier("offer.match")

                VelroField(
                    label: wantsReturn ? strings["ride.ask.fare_out"] : strings["driver.offer.title"],
                    text: Binding(get: { amount }, set: { amount = $0.filter(\.isNumber) }),
                    keyboard: .numberPad, identifier: "offer.amount"
                )
                if wantsReturn {
                    VelroField(
                        label: strings["ride.ask.fare_back"],
                        text: Binding(get: { returnAmount }, set: { returnAmount = $0.filter(\.isNumber) }),
                        keyboard: .numberPad, identifier: "offer.return"
                    )
                    if let minor, let returnMinor {
                        Text(strings["ride.ask.fare_total", ["amount": MoneyFormatter.format(Money(amountMinor: minor + returnMinor), strings: strings)]])
                            .velroFont(.heading, weight: .medium)
                            .foregroundStyle(Palette.onSurface)
                    }
                }
                VelroField(label: strings["driver.board.offer_note"], text: $note, identifier: "offer.note")

                if let error = model.error { InlineError(error: error) }

                PrimaryButton(label: strings["driver.offer.send"], enabled: ready && !busy, loading: busy) {
                    guard let minor else { return }
                    Task { await model.offer(request, amountMinor: minor, returnAmountMinor: wantsReturn ? returnMinor : nil, note: note) }
                }
                .accessibilityIdentifier("offer.send")
            }
            .padding(Spacing.gutter)
        }
        .background(Palette.background)
    }
}
