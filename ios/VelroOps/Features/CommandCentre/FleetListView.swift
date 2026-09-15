import SwiftUI
import VelroCore

/// The same drivers as the map, as a list: by state, then the ones the map
/// cannot usefully show -- far outside the area, or with no location at all
/// -- so none is simply missing.
struct FleetListView: View {
    @Bindable var model: FleetModel
    let snapshot: LiveMap

    @Environment(\.strings) private var strings

    var body: some View {
        let groups = FleetGroups(snapshot.drivers)
        let shown = model.visible
        List {
            if snapshot.drivers.isEmpty {
                FleetNoticeCard(systemImage: "moon.zzz", text: strings["admin.map.none_online"])
                    .listRowSeparator(.hidden)
                    .listRowBackground(Color.clear)
            } else if shown.isEmpty {
                FleetNoticeCard(systemImage: "line.3.horizontal.decrease.circle", text: strings["ops.map.no_match"])
                    .listRowSeparator(.hidden)
                    .listRowBackground(Color.clear)
            }

            ForEach(FleetCarState.allCases) { state in
                let rows = sorted(groups.onMap.filter { $0.carState == state && model.isShown($0) })
                if !rows.isEmpty {
                    Section {
                        ForEach(rows) { row($0) }
                    } header: {
                        header(strings[state.labelKey], count: rows.count) { FleetPinGlyph(state: state) }
                    }
                }
            }

            let faraway = sorted(groups.faraway.filter(model.isShown))
            if !faraway.isEmpty {
                Section {
                    ForEach(faraway) { row($0) }
                } header: {
                    header(strings["admin.map.outside_title"], count: faraway.count) {
                        Image(systemName: "globe.europe.africa").foregroundStyle(Palette.textMuted)
                    }
                }
            }

            let withoutFix = sorted(groups.withoutFix.filter(model.isShown))
            if !withoutFix.isEmpty {
                Section {
                    ForEach(withoutFix) { row($0) }
                } header: {
                    header(strings["admin.map.no_fix_title"], count: withoutFix.count) {
                        Image(systemName: "location.slash").foregroundStyle(Palette.textMuted)
                    }
                }
            }

            Section {
                FleetAsOfText(snapshot: snapshot)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .listRowBackground(Color.clear)
            }
        }
        #if os(iOS)
        .listStyle(.insetGrouped)
        #else
        .listStyle(.inset)
        #endif
        .scrollContentBackground(.hidden)
        .background(Palette.background)
    }

    private func sorted(_ drivers: [LiveDriver]) -> [LiveDriver] {
        drivers.sorted { $0.displayName(strings).localizedStandardCompare($1.displayName(strings)) == .orderedAscending }
    }

    private func header<Icon: View>(_ title: String, count: Int, @ViewBuilder icon: () -> Icon) -> some View {
        HStack(spacing: Spacing.s2) {
            icon()
            Text(title)
                .opsFont(.label, weight: .bold)
                .foregroundStyle(Palette.text)
            Text(OpsFormat.count(count, strings))
                .opsFont(.label)
                .monospacedDigit()
                .foregroundStyle(Palette.textMuted)
        }
        .textCase(nil)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isHeader)
    }

    private func row(_ driver: LiveDriver) -> some View {
        let isSelected = model.selectedID == driver.driverId
        return Button {
            model.selectedID = isSelected ? nil : driver.driverId
        } label: {
            FleetDriverRow(driver: driver)
        }
        .buttonStyle(.plain)
        .listRowBackground(isSelected ? Palette.bannerInfo : Palette.surface)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
        .contextMenu {
            if driver.location != nil {
                Button(strings["ops.map.show_on_map"], systemImage: "map") { model.showOnMap(driver) }
            }
        }
    }
}

/// One driver: who, which car, what he is doing, how old his position is.
struct FleetDriverRow: View {
    let driver: LiveDriver
    @Environment(\.strings) private var strings

    var body: some View {
        HStack(alignment: .top, spacing: Spacing.s3) {
            FleetPinGlyph(state: driver.glyphState, isTest: driver.rehearsing, diameter: 26)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: Spacing.s2) {
                    Text(driver.displayName(strings))
                        .opsFont(.body, weight: .medium)
                        .foregroundStyle(Palette.text)
                        .lineLimit(1)
                    if driver.rehearsing {
                        StatusChip(strings["admin.map.test"], tone: .attention)
                    }
                }
                if let vehicle = driver.vehicle {
                    HStack(spacing: Spacing.s1) {
                        LTRText(vehicle.plate)
                            .opsFont(.label, weight: .medium)
                        if let make = vehicle.makeAndModel {
                            // Separate runs, so the dot stays between the two
                            // in either direction instead of drifting to an end.
                            DotSeparator().opsFont(.label)
                            Text(make).opsFont(.label)
                        }
                    }
                    .foregroundStyle(Palette.textMuted)
                }
                if let trip = driver.trip {
                    Text(strings["admin.map.trip", ["number": "\u{2066}\(trip.number)\u{2069}"]] + "  "
                         + OpText.route(trip.originName, trip.destinationName, strings))
                        .opsFont(.label)
                        .foregroundStyle(Palette.text)
                        .lineLimit(2)
                }
                if let recorded = driver.location?.recorded {
                    HStack(spacing: Spacing.s1) {
                        if driver.location?.stale == true {
                            Image(systemName: "exclamationmark.triangle.fill")
                                .foregroundStyle(Palette.attention)
                                .accessibilityHidden(true)
                        }
                        DateText(recorded, style: .relative)
                    }
                    .opsFont(.caption)
                    .foregroundStyle(driver.location?.stale == true ? Palette.attention : Palette.textMuted)
                }
            }
            Spacer(minLength: Spacing.s2)
            StatusChip(availability: driver.availability)
        }
        .padding(.vertical, Spacing.s1)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}
