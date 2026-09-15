import MapKit
import SwiftUI
import VelroCore

/// Every working driver on one map, with the chips over it and the legend
/// under it.
///
/// The map is fed, never rebuilt: each refresh moves the pins (animated) and
/// leaves the camera where the operator put it.
struct FleetMapView: View {
    @Bindable var model: FleetModel
    let snapshot: LiveMap
    /// On a phone the panel is a sheet over the lower map: a car picked
    /// there is panned up into view.
    var revealsSelection = false

    /// The share of the screen's height the phone's panel leaves uncovered.
    static let uncoveredFraction: CGFloat = 0.46

    @Environment(\.strings) private var strings

    /// Pins that pass the filter and search, the ones on a trip drawn last.
    private var pins: [FleetPinItem] {
        model.visible
            .compactMap { driver in driver.coordinate.map { FleetPinItem(driver: driver, coordinate: $0) } }
            .sorted { $0.driver.carState.drawOrder < $1.driver.carState.drawOrder }
    }

    var body: some View {
        ZStack {
            map
                .ignoresSafeArea(edges: [.horizontal, .bottom])

            VStack(spacing: Spacing.s2) {
                Spacer(minLength: 0)
                notices
                HStack(alignment: .bottom, spacing: Spacing.s2) {
                    FleetLegendCard(model: model, snapshot: snapshot)
                    FleetMapButtons(model: model)
                }
            }
            .padding(Spacing.s3)
        }
    }

    private var map: some View {
        GeometryReader { geometry in
            baseMap
                .onChange(of: model.selectedID) { _, selected in
                    guard selected != nil else { return }
                    reveal(frame: geometry.frame(in: .global))
                }
        }
    }

    /// Pans -- never zooms -- so the car just picked sits between the chips
    /// and the phone's panel. A car already there is left alone; a choice the
    /// operator made, unlike a refresh, which never moves the camera.
    ///
    /// Worked from the region the map last reported over the map's own frame
    /// (the frame starts under the chips and runs to the screen's foot), not
    /// through a MapProxy: its conversions came back nil inside this layout.
    private func reveal(frame: CGRect) {
        guard revealsSelection, let coordinate = model.selected?.coordinate,
              frame.width > 0, frame.height > 0 else { return }
        let region = model.visibleRegion
        let screenHeight = frame.maxY
        // The band between the chips and the phone's panel, in points from
        // the map's top edge.
        let bandTop = max(0, screenHeight * 0.25 - frame.minY) + 24
        let bandBottom = screenHeight * Self.uncoveredFraction - frame.minY - 36
        guard bandBottom > bandTop else { return }
        let north = region.center.latitude + region.span.latitudeDelta / 2
        let west = region.center.longitude - region.span.longitudeDelta / 2
        let y = (north - coordinate.latitude) / region.span.latitudeDelta * frame.height
        let x = (coordinate.longitude - west) / region.span.longitudeDelta * frame.width
        let edge: CGFloat = 40
        let horizontallyInView = x >= edge && x <= frame.width - edge
        guard !(y >= bandTop && y <= bandBottom && horizontallyInView) else { return }
        // Move the centre by exactly the distance between where the car is
        // and where it should be, in degrees, keeping the span.
        let targetY = (bandTop + bandBottom) / 2
        let centre = CLLocationCoordinate2D(
            latitude: region.center.latitude - (y - targetY) / frame.height * region.span.latitudeDelta,
            longitude: horizontallyInView
                ? region.center.longitude
                : region.center.longitude + (x - frame.width / 2) / frame.width * region.span.longitudeDelta
        )
        model.move(to: MKCoordinateRegion(center: centre, span: region.span))
    }

    private var baseMap: some View {
        Map(position: $model.camera, interactionModes: [.pan, .zoom]) {
            ForEach(pins) { pin in
                let driver = pin.driver
                Annotation(driver.vehicle?.plate ?? "", coordinate: pin.coordinate, anchor: .center) {
                    Button {
                        model.selectedID = model.selectedID == driver.driverId ? nil : driver.driverId
                    } label: {
                        FleetPin(
                            state: driver.carState,
                            isTest: driver.rehearsing,
                            heading: driver.location?.headingDegrees,
                            isSelected: model.selectedID == driver.driverId
                        )
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(driver.accessibilitySummary(strings))
                    .accessibilityAddTraits(model.selectedID == driver.driverId ? [.isButton, .isSelected] : .isButton)
                }
                .annotationTitles(driver.vehicle == nil ? .hidden : .visible)
            }
        }
        .mapStyle(.standard(elevation: .flat, emphasis: .muted, pointsOfInterest: .excludingAll))
        .mapControls {
            MapCompass()
            MapScaleView()
            #if os(macOS)
            MapZoomStepper()
            #endif
        }
        .onMapCameraChange(frequency: .onEnd) { context in
            model.visibleRegion = context.region
        }
        // A picture of the ground: left to right in every language, as the
        // web panel's map is. What is written over it carries the reader's
        // direction itself.
        .environment(\.layoutDirection, .leftToRight)
        .accessibilityLabel(strings["admin.ops.live_map"])
    }

    /// Nobody online, or nobody passing the filter: said in words over the
    /// map, which stays usable underneath.
    @ViewBuilder private var notices: some View {
        if snapshot.drivers.isEmpty {
            FleetNoticeCard(systemImage: "moon.zzz", text: strings["admin.map.none_online"])
        } else if model.visible.isEmpty {
            FleetNoticeCard(systemImage: "line.3.horizontal.decrease.circle", text: strings["ops.map.no_match"])
        }
    }
}

struct FleetPinItem: Identifiable {
    let driver: LiveDriver
    let coordinate: CLLocationCoordinate2D
    var id: String { driver.driverId }
}

/// The two framing buttons, stacked as the system's map controls are.
private struct FleetMapButtons: View {
    let model: FleetModel
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(spacing: 0) {
            button("ops.map.fit_cars", systemImage: "scope") { model.fitCars() }
            Divider().frame(width: 28)
            button("ops.map.frame_region", systemImage: "map") { model.frameRegion() }
        }
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: Radius.md, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: Radius.md, style: .continuous).strokeBorder(Palette.border, lineWidth: 1)
        }
    }

    private func button(_ key: String, systemImage: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 17, weight: .medium))
                .frame(width: 44, height: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .foregroundStyle(Palette.accent)
        .help(strings[key])
        .accessibilityLabel(strings[key])
    }
}
