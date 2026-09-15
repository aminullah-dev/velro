import SwiftUI
import VelroCore

/// A selected car, in full: a sheet on iPhone, the inspector column on iPad
/// and Mac. Everything the web panel's popup says, and the two ways onward.
struct FleetDriverPanel: View {
    let driver: LiveDriver
    /// Offer "show on the map" -- from the list, where the map is not showing.
    let showMapAction: (() -> Void)?
    let close: () -> Void

    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.s4) {
                header
                if driver.location?.stale == true {
                    Banner(strings["admin.map.stale_warning"], tone: .warning, systemImage: "location.slash")
                }
                facts
                if let trip = driver.trip { tripCard(trip) }
                locationCard
                actions
            }
            .padding(Spacing.s4)
        }
        .scrollBounceBehavior(.basedOnSize)
        .background(Palette.background)
    }

    // MARK: Parts

    private var header: some View {
        HStack(alignment: .top, spacing: Spacing.s3) {
            FleetPinGlyph(state: driver.glyphState, isTest: driver.rehearsing, diameter: 40)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: Spacing.s1) {
                Text(driver.displayName(strings))
                    .opsFont(.title, weight: .bold)
                    .foregroundStyle(Palette.text)
                    .fixedSize(horizontal: false, vertical: true)
                FleetFlowLayout(spacing: Spacing.s1 + 2, lineSpacing: Spacing.s1) {
                    StatusChip(availability: driver.availability)
                    if driver.location?.stale == true {
                        StatusChip(strings["admin.map.stale"], tone: .attention)
                    }
                    if driver.rehearsing {
                        StatusChip(strings["admin.map.test_legend"], tone: .attention)
                    }
                }
            }
            Spacer(minLength: 0)
            Button(action: close) {
                Image(systemName: "xmark.circle.fill")
                    .font(.system(size: 24))
                    .symbolRenderingMode(.hierarchical)
                    .foregroundStyle(Palette.textMuted)
            }
            .buttonStyle(.plain)
            .keyboardShortcut(.cancelAction)
            .accessibilityLabel(strings["common.action.close"])
        }
    }

    private var facts: some View {
        VStack(alignment: .leading, spacing: Spacing.s3) {
            fact("admin.col.phone") { PhoneLink(driver.phone).opsFont(.body, weight: .medium) }
            Divider()
            fact("admin.col.plate") {
                if let vehicle = driver.vehicle {
                    VStack(alignment: .trailing, spacing: 2) {
                        LTRText(vehicle.plate).opsFont(.body, weight: .medium).foregroundStyle(Palette.text)
                        if let make = vehicle.makeAndModel {
                            Text(make).opsFont(.caption).foregroundStyle(Palette.textMuted)
                        }
                    }
                } else {
                    Text("—").foregroundStyle(Palette.textMuted)
                }
            }
        }
        .opsCard()
    }

    private func fact<Value: View>(_ labelKey: String, @ViewBuilder value: () -> Value) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: Spacing.s3) {
            Text(strings[labelKey])
                .opsFont(.label, weight: .regular)
                .foregroundStyle(Palette.textMuted)
            Spacer(minLength: Spacing.s2)
            value()
        }
        .accessibilityElement(children: .combine)
    }

    private func tripCard(_ trip: LiveDriver.Trip) -> some View {
        VStack(alignment: .leading, spacing: Spacing.s2) {
            HStack(spacing: Spacing.s2) {
                Image(systemName: "car.2.fill")
                    .foregroundStyle(Palette.accent)
                    .accessibilityHidden(true)
                Text(strings["admin.map.trip", ["number": trip.number]])
                    .opsFont(.heading, weight: .bold)
                    .foregroundStyle(Palette.text)
                Spacer(minLength: 0)
                StatusChip(trip: trip.status)
            }
            // Each place name its own isolate: Dari names in an English line
            // would otherwise turn the arrow round.
            Text(OpText.route(trip.originName, trip.destinationName, strings))
            .opsFont(.body)
            .foregroundStyle(Palette.text)
            .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
        .opsCard()
    }

    private var locationCard: some View {
        VStack(alignment: .leading, spacing: Spacing.s2) {
            if let location = driver.location {
                HStack(alignment: .firstTextBaseline, spacing: Spacing.s2) {
                    Image(systemName: location.stale ? "location.slash" : "location.fill")
                        .foregroundStyle(location.stale ? Palette.attention : Palette.accent)
                        .accessibilityHidden(true)
                    DateText(location.recorded, style: .relative)
                        .opsFont(.heading, weight: .bold)
                        .foregroundStyle(location.stale ? Palette.attention : Palette.text)
                }
                if let recorded = location.recorded {
                    Text(strings["admin.map.last_fix", ["time": OpsFormat.dateTime(recorded, strings)]])
                        .opsFont(.label, weight: .regular)
                        .foregroundStyle(Palette.textMuted)
                        .monospacedDigit()
                }
                LTRText(String(format: "%.5f, %.5f", location.latitude, location.longitude))
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
                    .textSelection(.enabled)
                if !driver.isInServiceArea {
                    Text(strings["admin.map.outside_title"])
                        .opsFont(.caption)
                        .foregroundStyle(Palette.attention)
                }
            } else {
                Label(strings["admin.map.no_fix_title"], systemImage: "location.slash")
                    .opsFont(.body)
                    .foregroundStyle(Palette.attention)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .opsCard()
    }

    @ViewBuilder private var actions: some View {
        VStack(spacing: Spacing.s2) {
            if let showMapAction, driver.location != nil {
                actionButton("ops.map.show_on_map", systemImage: "map", prominent: false, action: showMapAction)
            }
            if let trip = driver.trip, ops.can(.trips) {
                actionButton("ops.map.trip_details", systemImage: "car.2", prominent: true) {
                    ops.navigator.open(.trips, filter: "trip:\(trip.number)")
                }
            }
            if ops.can(.drivers) {
                actionButton("ops.map.driver_details", systemImage: "steeringwheel", prominent: driver.trip == nil) {
                    ops.navigator.open(.drivers, filter: "driver:\(driver.driverId)")
                }
            }
        }
    }

    @ViewBuilder
    private func actionButton(_ key: String, systemImage: String, prominent: Bool, action: @escaping () -> Void) -> some View {
        let label = Label(strings[key], systemImage: systemImage)
            .opsFont(.body, weight: .medium)
            .frame(maxWidth: .infinity)
            .padding(.vertical, Spacing.s1)
        if prominent {
            Button(action: action) { label }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
        } else {
            Button(action: action) { label }
                .buttonStyle(.bordered)
                .controlSize(.large)
        }
    }
}
