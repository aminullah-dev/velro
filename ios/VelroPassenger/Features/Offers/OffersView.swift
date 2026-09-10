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
        VelroScreen(title: strings["ride.offers.title"]) {
            content
                .padding(.horizontal, Spacing.gutter)
                .padding(.top, Spacing.md)
        }
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

    @ViewBuilder
    private var content: some View {
        if model.isLoading && model.request == nil {
            LoadingState()
        } else if let request = model.request {
            VStack(alignment: .leading, spacing: Spacing.md) {
                journey(request)
                if let error = model.error { InlineError(error: error) }

                // The status decides, not the emptiness of the list: once the
                // request expires the server says so on this very read, and a
                // screen branching on the list alone spins over "waiting" for
                // ever.
                if !request.isOpen && request.bookingId == nil {
                    Spacer()
                    RequestClosed(status: request.status) { app.router.replaceAll(with: .ask) }
                    Spacer()
                } else if !request.isOpen {
                    // Matched: already on the way to the booking.
                    LoadingState()
                } else if request.liveOffers.isEmpty {
                    Spacer()
                    waiting
                    Spacer()
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
                }
            }
            .padding(.bottom, Spacing.lg)
        } else if let error = model.error {
            ErrorState(error: error) { Task { await model.reload() } }
        } else {
            ErrorState(error: APIError(code: "RIDE_REQUEST_NOT_FOUND", httpStatus: 404)) {
                Task { await model.reload() }
            }
        }
    }

    private func journey(_ request: RideRequest) -> some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.xs) {
                Text(strings["ride.journey.from_to", [
                    "origin": request.originStationName ?? strings["common.value.unknown"],
                    "destination": request.destinationName ?? strings["common.value.unknown"],
                ]])
                .velroFont(.heading, weight: .medium)
                .foregroundStyle(Palette.onSurface)
                // The whole journey: on a round trip the outbound is half the ask.
                Text(strings["ride.offers.you_asked", ["amount": MoneyFormatter.format(request.askingTotal, strings: strings)]])
                    .velroFont(.label)
                    .foregroundStyle(Palette.onSurfaceVariant)
            }
        }
    }

    /// A spinner, because something really is coming: drivers are being shown
    /// this request now. An empty state would say the opposite.
    private var waiting: some View {
        VStack(spacing: Spacing.md) {
            ProgressView().controlSize(.large)
            Text(strings["ride.offers.waiting"])
                .velroFont(.body)
                .foregroundStyle(Palette.onSurfaceVariant)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .accessibilityIdentifier("offers.waiting")
    }

    private func offers(_ request: RideRequest) -> some View {
        ScrollView {
            LazyVStack(spacing: Spacing.sm) {
                ForEach(request.liveOffers) { offer in
                    OfferCard(
                        offer: offer,
                        photo: model.photos[offer.driverId],
                        asking: request.askingTotal,
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
}

private struct OfferCard: View {
    let offer: FareOffer
    let photo: UIImage?
    let asking: Money
    let accepting: Bool
    let enabled: Bool
    let accept: () -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.sm) {
                HStack(alignment: .top, spacing: Spacing.md) {
                    // The face before the name and the price: she is the one
                    // about to get into his car on an empty road.
                    DriverAvatar(photo: photo)
                    VStack(alignment: .leading, spacing: Spacing.xxs) {
                        Text(offer.driverName ?? strings["common.value.no_name"])
                            .velroFont(.heading, weight: .medium)
                            .foregroundStyle(Palette.onSurface)
                        HStack(spacing: Spacing.xs) {
                            if let rating = offer.driverRating {
                                Image(systemName: "star.fill")
                                    .font(.caption)
                                    .foregroundStyle(Palette.accent)
                                    .accessibilityHidden(true)
                                Text(Numerals.localise(String(format: "%.1f", rating), strings.locale))
                                    .velroFont(.caption, weight: .medium)
                            }
                            Text(strings["ride.offers.trips", ["count": offer.driverTrips ?? 0]])
                                .velroFont(.caption)
                                .foregroundStyle(Palette.onSurfaceVariant)
                        }
                    }
                    Spacer(minLength: Spacing.sm)
                    price
                }

                if let plate = offer.vehiclePlate {
                    HStack(spacing: Spacing.sm) {
                        // Read off a car: never mirrored, never in Eastern digits.
                        PlateText(plate: plate)
                        if let description = offer.vehicleDescription {
                            Text(description)
                                .velroFont(.caption)
                                .foregroundStyle(Palette.onSurfaceVariant)
                        }
                    }
                }

                if let note = offer.note {
                    Text(note)
                        .velroFont(.caption)
                        .foregroundStyle(Palette.onSurfaceVariant)
                }

                Divider().padding(.vertical, Spacing.xxs)

                PrimaryButton(label: strings["ride.offers.accept"], enabled: enabled, loading: accepting, action: accept)
                    .accessibilityIdentifier("offers.accept")
            }
        }
    }

    private var price: some View {
        VStack(alignment: .trailing, spacing: Spacing.xxs) {
            Text(MoneyFormatter.format(offer.total, strings: strings))
                .velroFont(.title, weight: .bold)
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
                .velroFont(.caption)
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

/// A number plate, as it reads on the metal.
struct PlateText: View {
    let plate: String

    var body: some View {
        Text(plate)
            .font(.system(.subheadline, design: .monospaced).weight(.semibold))
            .padding(.horizontal, Spacing.sm)
            .padding(.vertical, Spacing.xxs)
            .background(Palette.surfaceVariant, in: RoundedRectangle(cornerRadius: 6))
            .foregroundStyle(Palette.onSurface)
            .environment(\.layoutDirection, .leftToRight)
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
