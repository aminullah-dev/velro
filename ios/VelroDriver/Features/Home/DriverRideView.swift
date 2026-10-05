import SwiftUI
import VelroCore

/// On the road with passengers: the map, the road's next warning, who is in
/// the car, and the one next step -- "arrived at destination" -- because a
/// ride screen without it is a ride that cannot end. The same moment the
/// passenger's phone turns into her own ride map.
struct DriverRideView: View {
    let model: DriverHomeModel
    let help: () -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        ZStack {
            if let map = model.tripMap {
                JourneyMapView(map: map, vehicle: car, height: nil, fullBleed: true)
                    // Framed again once, when the first fix arrives: a map
                    // sized before his position was known can leave his own
                    // car off the edge of the screen.
                    .id(car == nil)
                    .ignoresSafeArea()
            } else {
                Palette.background.ignoresSafeArea()
            }

            VStack(spacing: Spacing.sm) {
                HStack(alignment: .top, spacing: Spacing.sm) {
                    RoadAheadBanner(next: model.roadAhead)
                    Button(action: help) {
                        Image(systemName: "sos")
                            .font(.headline)
                            .frame(width: Sizing.touchTarget, height: Sizing.touchTarget)
                            .foregroundStyle(Palette.onPrimary)
                            .background(Palette.error, in: Circle())
                            .shadow(color: .black.opacity(0.2), radius: 4, y: 2)
                    }
                    .accessibilityLabel(strings["safety.title"])
                    .accessibilityIdentifier("ride.help")
                }
                if model.app.duty.access == .denied { LocationOffBanner() }
                Spacer()
                DriverRideBar(assignment: model.assignment, busy: model.isBusy) {
                    Task { await model.advance() }
                }
                if let error = model.error {
                    InlineError(error: error)
                        .padding(.horizontal, Spacing.md)
                        .background(Palette.surface, in: RoundedRectangle(cornerRadius: Radius.md))
                }
            }
            .padding(.horizontal, Spacing.lg)
            .padding(.vertical, Spacing.sm)
        }
        .toolbar(.hidden, for: .navigationBar)
        .preference(key: BrandStatusBar.self, value: false)
        // He is driving: the screen stays on for as long as the map is up.
        .onAppear { UIApplication.shared.isIdleTimerDisabled = true }
        .onDisappear { UIApplication.shared.isIdleTimerDisabled = false }
    }

    /// His own car, drawn where the location feed says it is.
    private var car: VehicleLocation? {
        guard let fix = model.app.duty.position else { return nil }
        return VehicleLocation(latitude: fix.coordinate.latitude, longitude: fix.coordinate.longitude)
    }
}

/// The driver's strip at the foot of the ride map.
///
/// A driver glances down once between bends, so it says the three things he
/// decides on -- the fare he is owed for this run, the road he is on, and who
/// is aboard -- then the one next step, and gets back out of the way of the
/// map. The old strip showed his own name back to him and nothing he could use;
/// this one leads with the money, because that is what the run is for.
private struct DriverRideBar: View {
    let assignment: CurrentAssignment?
    let busy: Bool
    let advance: () -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        if let assignment {
            VStack(alignment: .leading, spacing: Spacing.md) {
                HStack(alignment: .top, spacing: Spacing.md) {
                    JourneyLine(origin: assignment.trip.originStationName,
                                destination: assignment.trip.destinationName, role: .label)
                    Spacer(minLength: Spacing.sm)
                    if let fare = totalFare(assignment) {
                        VStack(alignment: .trailing, spacing: Spacing.xxs) {
                            Text(strings["ride.label.fare"])
                                .velroFont(.caption)
                                .foregroundStyle(Palette.onSurfaceVariant)
                            Text(MoneyFormatter.format(fare, strings: strings))
                                .velroFont(.title, weight: .bold)
                                .foregroundStyle(Palette.primary)
                        }
                        .fixedSize()
                    }
                }

                let names = passengerNames(assignment)
                if !names.isEmpty {
                    Label {
                        Text(seatSuffix(assignment).isEmpty ? names : "\(names)  ·  \(seatSuffix(assignment))")
                            .velroFont(.label)
                            .foregroundStyle(Palette.onSurface)
                            .lineLimit(1)
                    } icon: {
                        Image(systemName: "person.2.fill")
                            .font(.caption)
                            .foregroundStyle(Palette.onSurfaceVariant)
                    }
                    .accessibilityElement(children: .combine)
                }

                if let next = assignment.trip.status.nextStep {
                    PrimaryButton(label: strings[next.actionKey], enabled: !busy, loading: busy, action: advance)
                        .accessibilityIdentifier("trip.next")
                }
            }
            .padding(Spacing.lg)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Palette.surface, in: RoundedRectangle(cornerRadius: Radius.card, style: .continuous))
            .shadow(color: .black.opacity(0.18), radius: 10, y: 3)
            .accessibilityIdentifier("ride.names")
        }
    }

    /// Every cash fare on the manifest, added up: what the whole run is worth
    /// to him, in the one line he looks for.
    private func totalFare(_ assignment: CurrentAssignment) -> Money? {
        let fares = assignment.passengers.compactMap(\.fare)
        guard let first = fares.first else { return nil }
        return fares.dropFirst().reduce(first, +)
    }

    private func passengerNames(_ assignment: CurrentAssignment) -> String {
        assignment.passengers.compactMap(\.passengerName).joined(separator: "، ")
    }

    private func seatSuffix(_ assignment: CurrentAssignment) -> String {
        let seats = assignment.passengers.reduce(0) { $0 + $1.seatCount }
        guard seats > 0 else { return "" }
        return strings["driver.label.passengers"] + " " + Numerals.format(seats, strings.locale)
    }
}
