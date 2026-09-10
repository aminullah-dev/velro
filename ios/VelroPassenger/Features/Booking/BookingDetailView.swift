import SwiftUI
import VelroCore

/// The booking: the code she shows the driver, the journey, the receipt, and
/// the driver once there is one.
struct BookingDetailView: View {
    @Environment(\.strings) private var strings
    @Environment(\.openURL) private var openURL
    @State private var model: BookingDetailModel
    @State private var helpOpen = false
    @State private var reportsAfterHelp = false
    @State private var confirmingCancel = false
    private let app: AppModel

    init(app: AppModel, bookingId: String) {
        self.app = app
        _model = State(initialValue: BookingDetailModel(app: app, bookingId: bookingId))
    }

    var body: some View {
        VelroScreen(title: model.booking?.number ?? strings["booking.title"]) {
            if let booking = model.booking {
                ScrollView {
                    content(booking)
                        .padding(.horizontal, Spacing.gutter)
                        .padding(.vertical, Spacing.md)
                }
                .refreshable { await model.refresh(asked: true) }
            } else if let error = model.error {
                ErrorState(error: error) { Task { await model.refresh(asked: true) } }
            } else {
                LoadingState()
            }
        }
        .task { await model.poll() }
        .sheet(isPresented: $helpOpen, onDismiss: {
            if reportsAfterHelp {
                reportsAfterHelp = false
                app.router.open(.reports)
            }
        }) {
            HelpSheet(app: app, ride: model.rideFacts, tripId: model.booking?.tripId, bookingId: model.booking?.id,
                      openReports: { reportsAfterHelp = true })
        }
        .confirmationDialog(strings["booking.action.cancel"], isPresented: $confirmingCancel, titleVisibility: .visible) {
            Button(strings["booking.action.cancel"], role: .destructive) { Task { await model.cancel() } }
                .accessibilityIdentifier("booking.cancel.confirm")
            Button(strings["common.action.back"], role: .cancel) {}
        }
    }

    @ViewBuilder
    private func content(_ booking: Booking) -> some View {
        VStack(alignment: .leading, spacing: Spacing.lg) {
            StatusChip(key: booking.status.messageKey, tone: booking.status.tone)

            if let map = model.map {
                // The small map is a door to the full tracking screen.
                Button { app.router.open(.track(booking.id)) } label: {
                    JourneyMapView(map: map, vehicle: model.vehicle)
                }
                .buttonStyle(.plain)
                .disabled(!booking.isActive)
                if booking.isActive {
                    TextAction(label: strings["track.open"]) { app.router.open(.track(booking.id)) }
                        .accessibilityIdentifier("booking.track")
                }
                if let vehicle = model.vehicle { VehicleAge(seconds: vehicle.ageSeconds) }
            }

            // Help at the top, on the journey she is taking -- not at the foot
            // of a scroll, because nobody scrolls in the moment it is needed.
            // Only while the ride is live: on a receipt it is noise, and noise
            // is what makes a real one get ignored.
            if booking.isActive {
                SecondaryButton(label: strings["safety.title"]) { helpOpen = true }
                    .accessibilityIdentifier("booking.help")
            }

            if model.isStale {
                Text(strings["common.state.offline"])
                    .velroFont(.caption)
                    .foregroundStyle(Palette.onSurfaceVariant)
            }
            if let error = model.error { InlineError(error: error) }

            if model.showsCode, let code = booking.verificationCode {
                BoardingCode(code: code)
            }

            VelroCard {
                VStack(alignment: .leading, spacing: Spacing.md) {
                    JourneyLine(origin: booking.pickupStationName, destination: booking.dropoffDestinationName)
                    if let departure = booking.departure {
                        Text(Calendars.dateTime(departure, strings.locale))
                            .velroFont(.label)
                            .foregroundStyle(Palette.onSurfaceVariant)
                    }
                    Receipt(booking: booking)
                }
            }

            // Absent until a driver is assigned: a state, not a gap.
            if booking.driverName != nil || booking.vehiclePlate != nil {
                VelroCard { driver(booking) }
            }

            if model.canCancel {
                SecondaryButton(label: strings["booking.action.cancel"], enabled: !model.isCancelling) {
                    confirmingCancel = true
                }
                .accessibilityIdentifier("booking.cancel")
            }

            if model.canRate {
                RatingPrompt { score in Task { await model.rate(score) } }
            }
            if model.ratingSubmitted {
                // Not the button's word: "Submit" says nothing about whether it was.
                Text(strings["rating.thanks"])
                    .velroFont(.label)
                    .foregroundStyle(Palette.primary)
            }
        }
    }

    private func driver(_ booking: Booking) -> some View {
        VStack(alignment: .leading, spacing: Spacing.xs) {
            Text(strings["receipt.label.driver"])
                .velroFont(.caption)
                .foregroundStyle(Palette.onSurfaceVariant)
            Text(booking.driverName ?? strings["common.value.no_name"])
                .velroFont(.body)
                .foregroundStyle(Palette.onSurface)
            if let plate = booking.vehiclePlate {
                Text(strings["receipt.label.vehicle"])
                    .velroFont(.caption)
                    .foregroundStyle(Palette.onSurfaceVariant)
                    .padding(.top, Spacing.xs)
                PlateText(plate: plate)
                if let description = booking.vehicleDescription {
                    Text(description)
                        .velroFont(.label)
                        .foregroundStyle(Palette.onSurfaceVariant)
                }
            }
            // Only while the journey is ahead: the server stops sending the
            // number once it is over, and it is never kept for a receipt.
            if let phone = booking.driverPhone {
                SecondaryButton(label: strings["booking.action.call_driver"]) {
                    if let url = URL(string: "tel:\(phone)") { openURL(url) }
                }
                .padding(.top, Spacing.sm)
            }
        }
    }
}

/// The receipt. The lines show only when they add up to the total: one that
/// does not add up is worse than one that only states the total.
private struct Receipt: View {
    let booking: Booking
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if booking.breakdownExplainsTotal, let lines = booking.fareBreakdown {
                ForEach(lines, id: \.self) { line in
                    FareRow(
                        label: (line.quantity ?? 1) > 1
                            ? strings["receipt.line.times", ["label": strings[line.key], "count": line.quantity ?? 1]]
                            : strings[line.key],
                        amount: line.total
                    )
                }
                Divider().padding(.vertical, Spacing.sm)
            }
            FareRow(label: strings["ride.label.fare"], amount: booking.fareTotal, bold: true)
            if let fee = booking.cancellationFee {
                FareRow(label: strings["receipt.label.cancellation_fee"], amount: fee)
                // Zero is worth saying rather than leaving to inference.
                if fee.amountMinor == 0 {
                    Text(strings["receipt.label.no_fee"])
                        .velroFont(.caption)
                        .foregroundStyle(Palette.onSurfaceVariant)
                }
            }
            Text(paymentMethod)
                .velroFont(.caption)
                .foregroundStyle(Palette.onSurfaceVariant)
                .padding(.top, Spacing.sm)
        }
    }

    private var paymentMethod: String {
        switch booking.paymentMethod {
        case "MOBILE_WALLET": strings["payment.method.mobile_wallet"]
        case "CARD": strings["payment.method.card"]
        case "CORPORATE": strings["payment.method.corporate"]
        default: strings["payment.method.cash"]
        }
    }
}

/// How old the car's position is, said out loud: "the car is here" and "the
/// car was here ten minutes ago" are different decisions about walking out.
struct VehicleAge: View {
    let seconds: Int
    @Environment(\.strings) private var strings

    var body: some View {
        Text(seconds < 90
             ? strings["trip.vehicle_seen_now"]
             : strings["trip.vehicle_seen", ["minutes": seconds / 60]])
            .velroFont(.caption)
            .foregroundStyle(Palette.onSurfaceVariant)
    }
}

private struct RatingPrompt: View {
    let rate: (Int) -> Void
    @State private var score = 0
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(spacing: Spacing.md) {
            Text(strings["rating.title"])
                .velroFont(.heading, weight: .medium)
                .foregroundStyle(Palette.onSurface)
            HStack(spacing: Spacing.sm) {
                ForEach(1...5, id: \.self) { star in
                    Button {
                        score = star
                        rate(star)
                    } label: {
                        Image(systemName: star <= score ? "star.fill" : "star")
                            .font(.title2)
                            .foregroundStyle(star <= score ? Palette.accent : Palette.outline)
                            .frame(minWidth: 44, minHeight: 44)
                    }
                    .accessibilityLabel(Numerals.format(star, strings.locale))
                }
            }
        }
        .frame(maxWidth: .infinity)
    }
}
