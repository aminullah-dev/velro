import SwiftUI
import VelroCore

/// Where from, opening on where the passenger is standing (ADR 0015).
///
/// Laid out the way the ride apps she may have used are: the current location
/// first, as one card that already knows the answer -- the district, the
/// station to walk to -- then the named places around, then where she asked
/// from last time, and the full list last. At a roadside, "where are you
/// going" should be one tap away, and typing should be a choice.
struct OriginPanel: View {
    @Bindable var model: AskModel
    let location: LocationService
    let openSettings: () -> Void
    @Environment(\.strings) private var strings
    /// The station she boards at: the nearest, unless she picked another.
    @State private var chosenStationId: String?

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: Spacing.sm) {
                hereCard

                let places = (model.whereabouts?.places ?? []).filter { $0.id != model.originPlace?.id }
                if !places.isEmpty {
                    sectionTitle(strings["origin.section.nearby"])
                    ForEach(places) { place in
                        PlaceRow(title: place.name, subtitle: place.distanceM.map(distance), systemImage: "mappin.and.ellipse") {
                            Task { await model.choose(place) }
                        }
                        .accessibilityIdentifier("origin.place")
                    }
                }

                if !model.recents.isEmpty {
                    sectionTitle(strings["origin.section.recent"])
                    ForEach(model.recents) { recent in
                        PlaceRow(
                            title: recent.placeName.map { strings["origin.place.saved", ["place": $0]] } ?? recent.stationName,
                            subtitle: recent.placeName == nil ? nil : recent.stationName,
                            systemImage: "clock.arrow.circlepath"
                        ) {
                            Task { await model.choose(recent) }
                        }
                        .accessibilityIdentifier("origin.recent")
                    }
                }

                PlaceRow(title: strings["origin.action.browse"], systemImage: "list.bullet") { model.browse() }
                    .accessibilityIdentifier("origin.browse")
                    .padding(.top, Spacing.xs)
            }
            .padding(.bottom, Spacing.xl)
        }
        .scrollDismissesKeyboard(.interactively)
        // Already allowed: find her as the flow opens, with no tap.
        .task {
            if location.access == .granted && model.here == .idle {
                await model.locate(using: location)
            }
        }
    }

    // MARK: The card

    private var hereCard: some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.sm) {
                HStack(spacing: Spacing.sm) {
                    Image(systemName: "location.fill")
                        .foregroundStyle(Palette.primary)
                        .accessibilityHidden(true)
                    Text(strings["origin.current.title"])
                        .velroFont(.heading, weight: .medium)
                        .foregroundStyle(Palette.onSurface)
                    Spacer()
                    if model.here == .locating { ProgressView() }
                }

                if location.access != .granted {
                    noAccess
                } else {
                    switch model.here {
                    case .idle, .locating:
                        muted(strings["origin.current.locating"])
                    case .unavailable:
                        muted(strings["origin.current.unavailable"])
                        SecondaryButton(label: strings["origin.action.retry_location"]) { locate() }
                    case .found:
                        if model.whereabouts?.inside == true {
                            found
                        } else {
                            muted(strings["origin.current.outside"])
                        }
                    }
                }
            }
        }
        .accessibilityIdentifier("origin.here")
    }

    @ViewBuilder
    private var noAccess: some View {
        if location.access == .denied {
            muted(strings["location.permission.denied"])
            SecondaryButton(label: strings["location.action.open_settings"], action: openSettings)
        } else {
            // Why, before iOS asks. Its own dialog explains nothing.
            muted(strings["location.permission.rationale"])
            PrimaryButton(label: strings["home.search.from_here"]) { locate() }
                .accessibilityIdentifier("origin.allow")
        }
    }

    @ViewBuilder
    private var found: some View {
        let here = model.whereabouts
        let stations = here?.stations ?? []
        let boarding = stations.first { $0.id == chosenStationId } ?? stations.first

        if let district = here?.district {
            HStack {
                Text(here?.districtIsGuess == true
                     ? strings["origin.current.district_guess", ["district": district.name]]
                     : strings["origin.current.district", ["district": district.name]])
                    .velroFont(.body)
                    .foregroundStyle(Palette.onSurface)
                Spacer()
                // Change is the list: a guessed district is corrected by
                // choosing the village, which is what was guessed at.
                TextAction(label: strings["origin.action.change_district"]) { model.browse() }
            }
        }

        if let boarding {
            // No distance when she is standing at it: "0 m away" reads as a fault.
            Text(strings["origin.current.nearest", ["station": boarding.name]]
                 + (boarding.distanceM.flatMap { $0 >= 50 ? " · " + distance($0) : nil } ?? ""))
                .velroFont(.body, weight: .medium)
                .foregroundStyle(Palette.onSurface)
        }

        if stations.count > 1 {
            muted(strings["origin.current.other_station"])
            FlowLayout {
                ForEach(stations.prefix(3)) { station in
                    ChoiceChip(label: station.name, selected: station.id == boarding?.id) {
                        chosenStationId = station.id
                    }
                }
            }
        }

        Divider().padding(.vertical, Spacing.xs)
        placeName

        PrimaryButton(
            label: strings["origin.current.use"],
            enabled: boarding != nil && !model.isNamingPlace,
            loading: model.isNamingPlace
        ) {
            guard let boarding else { return }
            Task { await model.travelFromHere(boardingAt: boarding) }
        }
        .accessibilityIdentifier("origin.use")
    }

    /// "What is this place called?" -- optional, never what stops her from
    /// travelling: leaving it empty is skipping it.
    @ViewBuilder
    private var placeName: some View {
        let typed = model.placeName.trimmingCharacters(in: .whitespacesAndNewlines)
        if let saved = model.originPlace, saved.name == typed {
            HStack(spacing: Spacing.sm) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(Palette.primary)
                    .accessibilityHidden(true)
                Text(strings["origin.place.saved", ["place": saved.name]])
                    .velroFont(.body, weight: .medium)
                    .foregroundStyle(Palette.onSurface)
                Spacer()
                TextAction(label: strings["origin.place.change"]) { model.clearPlace() }
            }
            if saved.pending { muted(strings["origin.place.pending"]) }
        } else if !model.canNamePlace {
            // A coarse fix: a field here would only collect a refusal.
            muted(strings["origin.place.need_precise"])
            if !location.isPrecise {
                TextAction(label: strings["location.action.open_settings"], action: openSettings)
            } else {
                TextAction(label: strings["origin.action.retry_location"]) { locate() }
            }
        } else {
            Text(strings["origin.place.question"])
                .velroFont(.label, weight: .medium)
                .foregroundStyle(Palette.onSurface)
            PlaceNameField(
                placeholder: strings["origin.place.hint"],
                text: $model.placeName,
                refused: model.placeRefusal != nil
            ) {
                Task { await model.savePlaceName() }
            }
            if let reason = model.placeRefusal {
                Text(strings[Naming.refusalKey(reason)])
                    .velroFont(.caption)
                    .foregroundStyle(Palette.error)
            } else {
                muted(strings["origin.place.why"])
            }
            if !typed.isEmpty {
                SecondaryButton(label: strings["origin.place.save"]) {
                    Task { await model.savePlaceName() }
                }
                .accessibilityIdentifier("origin.place_save")
            }
        }
    }

    // MARK: Pieces

    private func locate() {
        Task {
            await location.requestIfNeeded()
            await model.locate(using: location)
        }
    }

    private func distance(_ metres: Int) -> String {
        metres >= 1000
            ? strings["location.distance.kilometres", ["distance": metres / 1000]]
            : strings["location.distance.metres", ["distance": metres]]
    }

    private func sectionTitle(_ text: String) -> some View {
        Text(text)
            .velroFont(.label, weight: .medium)
            .foregroundStyle(Palette.onSurfaceVariant)
            .padding(.top, Spacing.md)
    }

    private func muted(_ text: String) -> some View {
        Text(text)
            .velroFont(.caption)
            .foregroundStyle(Palette.onSurfaceVariant)
            .fixedSize(horizontal: false, vertical: true)
    }
}

/// A name in Dari or Pashto, typed right to left.
///
/// Not `VelroField`: that one is for numbers and codes, so it forces left to
/// right and folds digits to Latin. A village's name is neither.
private struct PlaceNameField: View {
    let placeholder: String
    @Binding var text: String
    var refused = false
    let submit: () -> Void
    @FocusState private var focused: Bool

    var body: some View {
        TextField(placeholder, text: $text)
            .autocorrectionDisabled()
            .textInputAutocapitalization(.words)
            .submitLabel(.done)
            .onSubmit(submit)
            .font(.system(size: 18))
            .focused($focused)
            .padding(.horizontal, Spacing.lg)
            .frame(minHeight: Sizing.fieldHeight)
            .background(Palette.surface, in: RoundedRectangle(cornerRadius: Radius.md, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: Radius.md, style: .continuous)
                    .strokeBorder(
                        refused ? Palette.error : (focused ? Palette.primary : Palette.outline),
                        lineWidth: focused || refused ? 2 : 1
                    )
            )
            .accessibilityLabel(placeholder)
            .accessibilityIdentifier("origin.place_name")
    }
}
