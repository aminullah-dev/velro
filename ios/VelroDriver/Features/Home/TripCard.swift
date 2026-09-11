import SwiftUI
import VelroCore

/// The trip that is his: where, when, who, and the one next step.
struct TripCard: View {
    let model: DriverHomeModel
    let assignment: CurrentAssignment
    @Environment(\.strings) private var strings
    @Environment(\.openURL) private var openURL
    @State private var confirmingStart = false
    @State private var choosingReason = false

    /// The reason codes the server accepts, so the app cannot offer one that
    /// fails. Asked for, not optional: a cancellation with no reason cannot be
    /// told from any other afterwards.
    static let cancelReasons = ["VEHICLE_PROBLEM", "WEATHER", "DRIVER_CANCELLED", "OTHER"]

    var body: some View {
        let trip = assignment.trip
        VStack(alignment: .leading, spacing: Spacing.md) {
            VelroCard {
                VStack(alignment: .leading, spacing: Spacing.sm) {
                    HStack {
                        Text(trip.number)
                            .velroFont(.label)
                            .foregroundStyle(Palette.onSurfaceVariant)
                            .environment(\.layoutDirection, .leftToRight)
                        Spacer()
                        StatusChip(key: trip.status.messageKey, tone: trip.status.tone)
                    }
                    if let departure = trip.departure {
                        Text(Calendars.time(departure, strings.locale))
                            .velroFont(.title, weight: .bold)
                            .foregroundStyle(Palette.onSurface)
                    }
                    JourneyLine(origin: trip.originStationName, destination: trip.destinationName)
                    if let key = model.app.duty.roadAlertKey {
                        RoadAlertBanner(messageKey: key)
                    }
                    if let map = model.tripMap {
                        JourneyMapView(map: map)
                    }
                    ForEach(assignment.passengers) { rider in
                        Divider()
                        PassengerRow(
                            rider: rider,
                            rated: model.ratedBookings.contains(rider.bookingId),
                            call: { if let phone = rider.passengerPhone, let url = URL(string: "tel:\(phone)") { openURL(url) } },
                            rate: { score in Task { await model.rate(bookingId: rider.bookingId, score: score) } }
                        )
                    }
                }
            }

            if trip.status.acceptsBoardingCodes {
                VerifyCard(model: model)
            }

            if let next = trip.status.nextStep {
                PrimaryButton(label: strings[next.actionKey], enabled: !model.isBusy, loading: model.isBusy) {
                    if assignment.startsWithUnverified {
                        confirmingStart = true
                    } else {
                        Task { await model.advance() }
                    }
                }
                .accessibilityIdentifier("trip.next")
            }

            if trip.status.isCancellable {
                SecondaryButton(label: strings["driver.trip.cancel"], enabled: !model.isBusy) { choosingReason = true }
                    .accessibilityIdentifier("trip.cancel")
            }
        }
        // A question, not a wall: a passenger with a dead phone is ordinary on
        // this road. "Start" does exactly what the button always did.
        .alert(strings["driver.trip.start_unverified_title"], isPresented: $confirmingStart) {
            Button(strings["driver.trip.start_unverified_confirm"]) { Task { await model.advance() } }
            Button(strings["driver.trip.start_unverified_back"], role: .cancel) {}
        } message: {
            Text(strings["driver.trip.start_unverified_body", [
                "unverified": assignment.unverified,
                "total": assignment.passengers.count,
            ]])
        }
        .confirmationDialog(strings["driver.trip.cancel_title"], isPresented: $choosingReason, titleVisibility: .visible) {
            ForEach(Self.cancelReasons, id: \.self) { reason in
                Button(strings["cancel.reason.\(reason.lowercased())"], role: .destructive) {
                    Task { await model.cancelTrip(reason: reason) }
                }
            }
            Button(strings["common.action.cancel"], role: .cancel) {}
        } message: {
            Text(strings["driver.trip.cancel_hint"])
        }
    }
}

private struct PassengerRow: View {
    let rider: ManifestEntry
    let rated: Bool
    let call: () -> Void
    let rate: (Int) -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.xs) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: Spacing.xxs) {
                    Text(rider.passengerName ?? strings["booking.label.number"])
                        .velroFont(.label)
                        .foregroundStyle(Palette.onSurfaceVariant)
                    Text(rider.number)
                        .velroFont(.body, weight: .medium)
                        .foregroundStyle(Palette.onSurface)
                        .environment(\.layoutDirection, .leftToRight)
                }
                Spacer()
                if let fare = rider.fare {
                    Text(MoneyFormatter.format(fare, strings: strings))
                        .velroFont(.heading, weight: .bold)
                        .foregroundStyle(Palette.onSurface)
                }
            }
            if rider.isVerified {
                Label(strings["driver.verify.boarded"], systemImage: "checkmark.seal.fill")
                    .velroFont(.caption)
                    .foregroundStyle(Palette.primary)
                Stars(rated: rated, rate: rate)
            }
            if rider.passengerPhone != nil {
                SecondaryButton(label: strings["driver.action.call_passenger"], action: call)
            }
        }
    }
}

private struct Stars: View {
    let rated: Bool
    let rate: (Int) -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        if rated {
            Text(strings["rating.thanks"])
                .velroFont(.caption)
                .foregroundStyle(Palette.primary)
        } else {
            VStack(alignment: .leading, spacing: 0) {
                Text(strings["rating.hint"])
                    .velroFont(.caption)
                    .foregroundStyle(Palette.onSurfaceVariant)
                HStack(spacing: 0) {
                    ForEach(1...5, id: \.self) { star in
                        Button { rate(star) } label: {
                            Image(systemName: "star")
                                .font(.title3)
                                .foregroundStyle(Palette.outline)
                                .frame(minWidth: 44, minHeight: 44)
                        }
                        .accessibilityLabel(Numerals.localise(String(star), strings.locale))
                    }
                }
            }
        }
    }
}

/// The passenger reads out the code on her phone; he types it here.
private struct VerifyCard: View {
    @Bindable var model: DriverHomeModel
    @Environment(\.strings) private var strings

    var body: some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.md) {
                Text(strings["driver.action.verify_passenger"])
                    .velroFont(.heading, weight: .medium)
                    .foregroundStyle(Palette.onSurface)
                TextField("", text: Binding(
                    get: { model.verifyingCode },
                    set: { model.verifyingCode = Numerals.latin($0).uppercased() }
                ))
                .textInputAutocapitalization(.characters)
                .autocorrectionDisabled()
                .font(.system(size: 26, weight: .semibold, design: .monospaced))
                .multilineTextAlignment(.center)
                .frame(minHeight: Sizing.fieldHeight)
                .background(Palette.surface, in: RoundedRectangle(cornerRadius: Radius.md, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: Radius.md, style: .continuous).strokeBorder(Palette.outline, lineWidth: 1))
                .environment(\.layoutDirection, .leftToRight)
                .accessibilityLabel(strings["driver.action.verify_passenger"])
                .accessibilityIdentifier("trip.code")
                SecondaryButton(label: strings["driver.action.verify_passenger"], enabled: model.verifyingCode.count >= 3 && !model.isBusy) {
                    Task { await model.verify() }
                }
                .accessibilityIdentifier("trip.verify")
                if let number = model.lastVerified {
                    Label(number, systemImage: "checkmark.circle.fill")
                        .velroFont(.label)
                        .foregroundStyle(Palette.primary)
                        .environment(\.layoutDirection, .leftToRight)
                }
            }
        }
    }
}

/// The advisory zone the car is inside, loud enough to read at speed.
struct RoadAlertBanner: View {
    let messageKey: String
    @Environment(\.strings) private var strings

    var body: some View {
        Label(strings[messageKey], systemImage: "exclamationmark.triangle.fill")
            .velroFont(.heading, weight: .bold)
            .foregroundStyle(Palette.onToneFailed)
            .frame(maxWidth: .infinity)
            .padding(Spacing.md)
            .background(Palette.toneFailed, in: RoundedRectangle(cornerRadius: Radius.md, style: .continuous))
            .accessibilityIdentifier("trip.road_alert")
    }
}
