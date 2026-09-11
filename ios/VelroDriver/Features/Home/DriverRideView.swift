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
                RideNames(
                    driver: model.profile?.fullName,
                    passenger: model.assignment?.passengers.compactMap(\.passengerName).joined(separator: "، ")
                )
                if let next = model.assignment?.trip.status.nextStep {
                    PrimaryButton(label: strings[next.actionKey], enabled: !model.isBusy, loading: model.isBusy) {
                        Task { await model.advance() }
                    }
                    .shadow(color: .black.opacity(0.15), radius: 6, y: 2)
                    .accessibilityIdentifier("trip.next")
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
