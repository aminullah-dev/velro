import SwiftUI
import VelroCore

/// The drivers who answered, cheapest journey first, each with a face.
struct OffersView: View {
    @Environment(\.strings) private var strings
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var model: OffersModel
    private let app: AppModel

    init(app: AppModel) {
        self.app = app
        _model = State(initialValue: OffersModel(app: app))
    }

    var body: some View {
        GeometryReader { geometry in
            if geometry.size.width >= Wide.threshold {
                wide(geometry)
            } else {
                compact(geometry)
            }
        }
        .background(Palette.background)
        .navigationTitle(strings["ride.offers.title"])
        .navigationBarTitleDisplayMode(.inline)
        // The title is on the sheet; the bar is only its floating back button.
        .toolbarBackground(.hidden, for: .navigationBar)
        .toolbar { ToolbarItem(placement: .principal) { Color.clear.frame(width: 1, height: 1).accessibilityHidden(true) } }
        .task { await model.poll() }
        // The moment a price is agreed the journey exists, so she is taken to
        // it, with home underneath -- not left on prices that no longer matter.
        .onChange(of: model.agreedBookingId) { _, booking in
            if let booking { app.router.replaceAll(with: .booking(booking)) }
        }
        .onChange(of: model.cancelled) { _, cancelled in
            if cancelled { app.router.home() }
        }
    }

    /// Unfolded: the road across the whole screen, the answers on a panel
    /// standing at its side.
    private func wide(_ geometry: GeometryProxy) -> some View {
        ZStack(alignment: .topLeading) {
            if let map = model.map {
                JourneyMapView(map: map, height: nil, fullBleed: true)
                    .ignoresSafeArea()
            }
            ScrollView {
                content(grabber: false)
                    .padding(.horizontal, Spacing.gutter)
                    .padding(.vertical, Spacing.lg)
            }
            .scrollIndicators(.hidden)
            .frame(width: Wide.panel)
            .floatingPanel()
            .padding(.leading, Spacing.gutter)
            .padding(.bottom, Spacing.lg)
        }
    }

    private func compact(_ geometry: GeometryProxy) -> some View {
        let mapHeight = geometry.size.height * 0.42 + geometry.safeAreaInsets.top
        return ZStack(alignment: .top) {
                // The road first, as inDrive and its kind open: the journey she
                // is pricing, drawn, so the prices below land on a place rather
                // than on a line of text. Behind everything, edge to edge.
                if let map = model.map {
                    JourneyMapView(map: map, height: mapHeight, fullBleed: true)
                        .ignoresSafeArea(edges: .top)
                }
                ScrollView {
                    VStack(spacing: 0) {
                        Color.clear
                            .frame(height: model.map == nil ? Spacing.sm : max(mapHeight - geometry.safeAreaInsets.top - Radius.sheet, 0))
                            .accessibilityHidden(true)
                        content
                            .padding(.horizontal, Spacing.gutter)
                            .padding(.bottom, Spacing.xl)
                            .frame(minHeight: geometry.size.height * 0.62, alignment: .top)
                            .sheetPanel()
                    }
                }
                .scrollIndicators(.hidden)
            }
    }

    private var content: some View { content(grabber: true) }

    @ViewBuilder
    private func content(grabber: Bool) -> some View {
        VStack(alignment: .leading, spacing: Spacing.lg) {
            if grabber { SheetGrabber() }
            Text(strings["ride.offers.title"])
                .velroFont(.headline)
                .foregroundStyle(Palette.onSurface)
                .accessibilityAddTraits(.isHeader)

            if model.isLoading && model.request == nil {
                LoadingState()
            } else if let request = model.request {
                journey(request)
                if let error = model.error { InlineError(error: error) }

                // The status decides, not the emptiness of the list: once the
                // request expires the server says so on this very read, and a
                // screen branching on the list alone spins over "waiting" for
                // ever.
                if !request.isOpen && request.bookingId == nil {
                    RequestClosed(status: request.status) { app.router.replaceAll(with: .ask) }
                        .padding(.vertical, Spacing.xl)
                } else if !request.isOpen {
                    // Matched: already on the way to the booking.
                    LoadingState()
                } else if request.liveOffers.isEmpty {
                    waiting
                } else {
                    offers(request)
                }

                // Only while there is something to cancel. Back, by contrast,
                // leaves the request open: drivers are still bidding on it.
                if request.isOpen {
                    SecondaryButton(
                        label: strings["ride.action.cancel"],
                        enabled: !model.isCancelling && model.acceptingOfferId == nil
                    ) {
                        Task { await model.cancel() }
                    }
                    .accessibilityIdentifier("offers.cancel")
                    .padding(.top, Spacing.sm)
                }
            } else if let error = model.error {
                ErrorState(error: error) { Task { await model.reload() } }
            } else {
                ErrorState(error: APIError(code: "RIDE_REQUEST_NOT_FOUND", httpStatus: 404)) {
                    Task { await model.reload() }
                }
            }
        }
    }

    private func journey(_ request: RideRequest) -> some View {
        VStack(alignment: .leading, spacing: Spacing.sm) {
            JourneyLine(origin: request.originStationName, destination: request.destinationName, role: .body)
            if let place = request.originPlaceName {
                Text(strings["ride.journey.from_place", ["place": place]])
                    .velroFont(.label)
                    .foregroundStyle(Palette.primary)
            }
            // The whole journey: on a round trip the outbound is half the ask.
            Label {
                Text(strings["ride.offers.you_asked", ["amount": MoneyFormatter.format(request.askingTotal, strings: strings)]])
                    .velroFont(.label, weight: .medium)
            } icon: {
                Image(systemName: "banknote").font(.footnote)
            }
            .foregroundStyle(Palette.onSurfaceVariant)
        }
        .padding(Spacing.lg)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Palette.surface.opacity(0.7), in: RoundedRectangle(cornerRadius: Radius.card, style: .continuous))
    }

    /// Rings spreading from a car, because something really is coming:
    /// drivers are being shown this request now. An empty state would say
    /// the opposite.
    private var waiting: some View {
        VStack(spacing: Spacing.md) {
            RadarPulse()
            Text(strings["ride.offers.waiting"])
                .velroFont(.body)
                .foregroundStyle(Palette.onSurfaceVariant)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, Spacing.lg)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("offers.waiting")
    }

    private func offers(_ request: RideRequest) -> some View {
        // Worth pointing at only in a crowd: with one reply there is no
        // "cheapest", and a badge on the only card is noise. The list is
        // already cheapest-first, so the best price is its head.
        let bestId = request.liveOffers.count > 1 ? request.liveOffers.first?.id : nil
        return LazyVStack(spacing: Spacing.lg) {
            ForEach(request.liveOffers) { offer in
                OfferCard(
                    offer: offer,
                    photo: model.photos[offer.driverId],
                    asking: request.askingTotal,
                    best: offer.id == bestId,
                    accepting: model.acceptingOfferId == offer.id,
                    enabled: model.acceptingOfferId == nil
                ) {
                    Task { await model.accept(offer) }
                }
                // This list changes under her finger: a reply can arrive as
                // she reaches for Accept. The insert is animated so the
                // shift is something the eye can follow -- otherwise she
                // agrees a fare with the wrong driver.
                .transition(reduceMotion ? .opacity : .move(edge: .top).combined(with: .opacity))
            }
        }
        .animation(reduceMotion ? nil : .spring(duration: 0.35), value: request.liveOffers.map(\.id))
    }
}

/// One driver's answer, laid out as ride apps lay out a car: the price
/// first and largest, the face beside it, then who he is and what he drives.
private struct OfferCard: View {
    let offer: FareOffer
    let photo: UIImage?
    let asking: Money
    var best = false
    let accepting: Bool
    let enabled: Bool
    let accept: () -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.md) {
            HStack(alignment: .top, spacing: Spacing.md) {
                price
                Spacer(minLength: Spacing.sm)
                // The face before the name: she is the one about to get into
                // his car on an empty road.
                DriverAvatar(photo: photo, size: 64)
            }

            VStack(alignment: .leading, spacing: Spacing.xs) {
                Text(offer.driverName ?? strings["common.value.no_name"])
                    .velroFont(.heading, weight: .bold)
                    .foregroundStyle(Palette.onSurface)
                HStack(spacing: Spacing.sm) {
                    if let rating = offer.driverRating {
                        StarRating(rating: rating)
                        Text(Numerals.localise(String(format: "%.1f", rating), strings.locale))
                            .velroFont(.caption, weight: .medium)
                            .foregroundStyle(Palette.onSurface)
                    }
                    Text(strings["ride.offers.trips", ["count": offer.driverTrips ?? 0]])
                        .velroFont(.caption)
                        .foregroundStyle(Palette.onSurfaceVariant)
                }
                .accessibilityElement(children: .combine)
            }

            if let plate = offer.vehiclePlate {
                HStack(spacing: Spacing.sm) {
                    Image(systemName: "car.fill")
                        .font(.footnote)
                        .foregroundStyle(Palette.primary)
                        .accessibilityHidden(true)
                    // Read off a car: never mirrored, never in Eastern digits.
                    PlateText(plate: plate)
                    if let description = offer.vehicleDescription {
                        Text(description)
                            .velroFont(.caption)
                            .foregroundStyle(Palette.onSurfaceVariant)
                            .lineLimit(1)
                    }
                }
            }

            if let note = offer.note {
                Text(note)
                    .velroFont(.caption)
                    .foregroundStyle(Palette.onSurfaceVariant)
            }

            PrimaryButton(label: strings["ride.offers.accept"], enabled: enabled, loading: accepting, action: accept)
                .accessibilityIdentifier("offers.accept")
                .padding(.top, Spacing.xs)
        }
        .padding(Spacing.lg)
        .padding(.top, best ? Spacing.sm : 0)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Palette.surface, in: RoundedRectangle(cornerRadius: Radius.card, style: .continuous))
        // The best price wears the green edge; the rest sit quiet, so the eye
        // lands on it first without a word being shouted.
        .overlay(
            RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
                .strokeBorder(best ? Palette.primary : Palette.outlineVariant, lineWidth: best ? 2 : 1)
        )
        .elevation(.low)
        // The cheapest reply, named on a tag hung on its edge. A ride app
        // does not make her compare numbers on a roadside: it points.
        .overlay(alignment: .topLeading) {
            if best {
                Label {
                    Text(strings["ride.offers.best_price"]).velroFont(.caption, weight: .bold)
                } icon: {
                    Image(systemName: "arrow.down.circle.fill").font(.caption)
                }
                .foregroundStyle(Palette.onPrimary)
                .padding(.horizontal, Spacing.md)
                .padding(.vertical, Spacing.xs)
                .background(Palette.primary, in: Capsule())
                .offset(x: Spacing.lg, y: -Spacing.md)
                .accessibilityElement(children: .combine)
            }
        }
        .padding(.top, best ? Spacing.md : 0)
    }

    private var price: some View {
        VStack(alignment: .leading, spacing: Spacing.xxs) {
            Text(MoneyFormatter.format(offer.total, strings: strings))
                .velroFont(.headline)
                .foregroundStyle(Palette.onSurface)
            // The two legs under the total, on a round trip only.
            if let back = offer.returnAmount {
                Text(strings["ride.offers.leg_out"] + " " + MoneyFormatter.format(offer.amount, strings: strings)
                     + "  ·  " + strings["ride.offers.leg_back"] + " " + MoneyFormatter.format(back, strings: strings))
                    .velroFont(.caption)
                    .foregroundStyle(Palette.onSurfaceVariant)
            }
            // How it compares with what was asked, so nobody subtracts at a
            // roadside.
            let difference = offer.difference(from: asking)
            // Signed through the formatter, not by gluing "+" on the front:
            // in a right-to-left line a bare sign drifts to the far side of
            // Eastern digits (Android's offer card still does this).
            Text(difference == 0
                 ? strings["ride.offers.same_as_asked"]
                 : MoneyFormatter.format(minor: difference, currency: asking.currency, strings: strings, showPlus: true))
                .velroFont(.label, weight: .medium)
                .foregroundStyle(difference <= 0 ? Palette.primary : Palette.onSurfaceVariant)
        }
    }
}

/// A driver's photograph, or a silhouette while it loads or when the server
/// declines to show it.
struct DriverAvatar: View {
    let photo: UIImage?
    var size: CGFloat = 48

    var body: some View {
        Group {
            if let photo {
                Image(uiImage: photo).resizable().scaledToFill()
            } else {
                Image(systemName: "person.fill")
                    .font(.system(size: size * 0.45))
                    .foregroundStyle(Palette.onSurfaceVariant)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(Palette.surfaceVariant)
            }
        }
        .frame(width: size, height: size)
        .clipShape(Circle())
        .accessibilityHidden(true)
    }
}

/// The request ended without a ride: expired, or cancelled from another phone.
/// Nothing left to wait for, so the way back to asking, not a spinner.
private struct RequestClosed: View {
    let status: RideRequestStatus
    let askAgain: () -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        let expired = status == .expired
        VStack(spacing: Spacing.md) {
            Text(strings[expired ? "ride.offers.expired_title" : "ride.offers.cancelled_title"])
                .velroFont(.heading, weight: .medium)
                .foregroundStyle(Palette.onSurface)
            Text(strings[expired ? "ride.offers.expired_body" : "ride.offers.cancelled_body"])
                .velroFont(.label)
                .foregroundStyle(Palette.onSurfaceVariant)
                .multilineTextAlignment(.center)
            PrimaryButton(label: strings["ride.offers.ask_again"], action: askAgain)
        }
        .frame(maxWidth: .infinity)
    }
}
