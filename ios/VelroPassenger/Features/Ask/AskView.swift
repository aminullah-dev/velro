import SwiftUI
import VelroCore

/// Asking for a ride: five steps in one frame, each sliding in from the side
/// it comes from, with back stepping back rather than leaving the whole form.
struct AskView: View {
    @Environment(\.strings) private var strings
    @Environment(\.openURL) private var openURL
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var model: AskModel
    @State private var location = LocationService()
    private let app: AppModel

    init(app: AppModel) {
        self.app = app
        _model = State(initialValue: AskModel(app: app))
    }

    var body: some View {
        VelroScreen(title: strings[model.step.titleKey]) {
            VStack(alignment: .leading, spacing: Spacing.md) {
                StepProgress(current: model.step.rawValue, total: AskModel.Step.allCases.count)

                if let error = model.error, model.isEmptyForStep, !model.isLoading {
                    ErrorState(error: error) { Task { await model.retry() } }
                } else {
                    if let error = model.error {
                        InlineError(error: error)
                        if model.needsLocationAccess && location.access != .granted {
                            LocationNote(access: location.access, openSettings: openSettings)
                        }
                    }
                    ZStack {
                        panel
                            .id(model.step)
                            .transition(transition)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
                }
            }
            .padding(.horizontal, Spacing.gutter)
            .padding(.top, Spacing.md)
            .animation(reduceMotion ? .none : .easeInOut(duration: 0.22), value: model.step)
        }
        // Back steps back. The system button, and the swipe beside it, would
        // leave the whole flow and throw away every answer given so far --
        // on a phone those are the same intention.
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .topBarLeading) {
                Button {
                    if !model.back() { app.router.back() }
                } label: {
                    Image(systemName: "chevron.backward")
                        .font(.body.weight(.semibold))
                        .frame(minWidth: 44, minHeight: 44)
                }
                .accessibilityLabel(strings["common.action.back"])
                .accessibilityIdentifier("ask.back")
            }
        }
        .task { await model.start() }
    }

    private var transition: AnyTransition {
        guard !reduceMotion else { return .opacity }
        return .asymmetric(
            insertion: .move(edge: model.forward ? .trailing : .leading).combined(with: .opacity),
            removal: .move(edge: model.forward ? .leading : .trailing).combined(with: .opacity)
        )
    }

    @ViewBuilder
    private var panel: some View {
        if model.isLoading {
            LoadingState()
        } else {
            switch model.step {
            case .district: districtList
            case .village: villageList
            case .station: stationList
            case .destination: destinationList
            case .ask: askForm
            }
        }
    }

    // MARK: Places

    private var districtList: some View {
        ScrollView {
            LazyVStack(spacing: Spacing.sm) {
                ForEach(model.districts) { district in
                    PlaceRow(title: district.name, subtitle: district.alternativeName) { model.choose(district) }
                        .accessibilityIdentifier("ask.district")
                }
            }
            .padding(.bottom, Spacing.xl)
        }
        .scrollIndicators(.hidden)
    }

    private var villageList: some View {
        VStack(spacing: Spacing.sm) {
            if model.villages.count > 12 {
                VelroField(label: strings["geo.action.filter_villages"], text: $model.villageFilter, identifier: "ask.filter")
            }
            if model.shownVillages.isEmpty {
                EmptyState(key: "empty.search_results")
            } else {
                ScrollView {
                    LazyVStack(spacing: Spacing.sm) {
                        ForEach(model.shownVillages) { village in
                            PlaceRow(title: village.name) { model.choose(village) }
                                .accessibilityIdentifier("ask.village")
                        }
                    }
                    .padding(.bottom, Spacing.xl)
                }
                .scrollDismissesKeyboard(.immediately)
            }
        }
    }

    @ViewBuilder
    private var stationList: some View {
        // A village whose stations were never downloaded is a real morning in
        // Ghorband; it gets a sentence and a way forward, not a blank screen.
        if model.stations.isEmpty {
            EmptyState(key: "empty.stations", systemImage: "mappin.slash",
                       actionKey: "empty.action.search_again") { Task { await model.retry() } }
        } else {
            ScrollView {
                LazyVStack(spacing: Spacing.sm) {
                    ForEach(model.stations) { station in
                        PlaceRow(title: station.name, subtitle: subtitle(for: station), systemImage: "mappin.circle.fill") {
                            Task { await model.choose(station) }
                        }
                        .accessibilityIdentifier("ask.station")
                    }
                }
                .padding(.bottom, Spacing.xl)
            }
        }
    }

    private func subtitle(for station: Station) -> String? {
        if let description = station.description { return description }
        guard let metres = station.distanceM else { return nil }
        return metres >= 1000
            ? strings["location.distance.kilometres", ["distance": metres / 1000]]
            : strings["location.distance.metres", ["distance": metres]]
    }

    /// Internal destinations, then external; Kabul opens into Khair Khana,
    /// Mina and Jada rather than standing as one vague choice.
    private var destinationList: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: Spacing.sm) {
                ForEach(model.destinationGroups) { group in
                    destinationGroup(group)
                }
                passengerPicker
                    .padding(.top, Spacing.lg)
            }
            .padding(.bottom, Spacing.xl)
        }
    }

    @ViewBuilder
    private func destinationGroup(_ group: DestinationGroup) -> some View {
        let expanded = model.expandedGroupId == group.id
        Button {
            withAnimation(.snappy) { model.toggle(group) }
        } label: {
            VelroCard {
                HStack {
                    Text(group.name)
                        .velroFont(.body, weight: model.destination?.id == group.id ? .medium : .regular)
                        .foregroundStyle(Palette.onSurface)
                    Spacer()
                    Image(systemName: group.isChoosableItself ? "chevron.forward" : (expanded ? "minus" : "plus"))
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(group.isChoosableItself ? Palette.outline : Palette.primary)
                        .accessibilityHidden(true)
                }
            }
        }
        .buttonStyle(PressStyle())
        .accessibilityIdentifier("ask.destination")
        .accessibilityAddTraits(group.isChoosableItself ? [] : .isHeader)

        if expanded {
            ForEach(group.children) { child in
                PlaceRow(title: child.name, emphasised: model.destination?.id == child.id) { model.choose(child) }
                    .padding(.leading, Spacing.xl)
                    .accessibilityIdentifier("ask.destination.child")
            }
        }
    }

    private var passengerPicker: some View {
        VStack(alignment: .leading, spacing: Spacing.sm) {
            Text(strings["ride.ask.passengers"])
                .velroFont(.label, weight: .medium)
                .foregroundStyle(Palette.onSurface)
            HStack(spacing: Spacing.sm) {
                ForEach(1...4, id: \.self) { count in
                    ChoiceChip(label: Numerals.format(count, strings.locale), selected: model.form.passengers == count) {
                        model.form.passengers = count
                    }
                }
            }
        }
    }

    // MARK: The ask

    /// Naming a price. No suggested fare and no "typical price": VELRO does
    /// not know one, and a number the platform invented would anchor every
    /// negotiation in Ghorband to a guess made in a database.
    private var askForm: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.lg) {
                VelroCard {
                    VStack(alignment: .leading, spacing: Spacing.xs) {
                        Text(strings["ride.journey.from_to", [
                            "origin": model.station?.name ?? strings["common.value.unknown"],
                            "destination": model.destination?.name ?? strings["common.value.unknown"],
                        ]])
                        .velroFont(.heading, weight: .medium)
                        .foregroundStyle(Palette.onSurface)
                        Text(strings["ride.ask.hint"])
                            .velroFont(.label)
                            .foregroundStyle(Palette.onSurfaceVariant)
                    }
                }

                AmountField(
                    // "Fare there" once there is a way back to tell it from.
                    label: strings[isRoundTrip ? "ride.ask.fare_out" : "ride.ask.title"],
                    text: $model.form.offeredFare,
                    identifier: "ask.fare"
                )

                passengerPicker

                DeparturePicker(form: $model.form)

                VelroField(label: strings["ride.ask.note"], text: $model.form.note, identifier: "ask.note")

                // Why iOS is about to ask, said before it asks -- or, once it
                // has stopped asking, where the switch went.
                if !model.needsLocationAccess && location.access != .granted {
                    LocationNote(access: location.access, openSettings: openSettings)
                }

                PrimaryButton(label: strings["ride.ask.action"], enabled: model.canAsk, loading: model.isSubmitting) {
                    Task { await send() }
                }
                .accessibilityIdentifier("ask.send")
            }
            .padding(.bottom, Spacing.xl)
        }
        .scrollDismissesKeyboard(.interactively)
    }

    private var isRoundTrip: Bool { model.form.returnAfterDays != nil }

    /// The first ask asks iOS for the location if it never has. A refusal is
    /// not a wall: the ask goes anyway, and the server answers.
    private func send() async {
        await location.requestIfNeeded()
        let fix = await location.currentFix()
        if await model.ask(latitude: fix?.coordinate.latitude, longitude: fix?.coordinate.longitude) {
            // Home underneath, the prices on top: back from them is home.
            app.router.replaceAll(with: .offers)
        }
    }

    private func openSettings() {
        if let url = URL(string: UIApplication.openSettingsURLString) { openURL(url) }
    }
}

/// A price, the one large control on the screen, with its currency beside it.
struct AmountField: View {
    let label: String
    @Binding var text: String
    var identifier = ""
    @Environment(\.strings) private var strings
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.xs) {
            Text(label)
                .velroFont(.label)
                .foregroundStyle(Palette.onSurfaceVariant)
            HStack(spacing: Spacing.sm) {
                TextField("", text: Binding(get: { text }, set: { text = Numerals.latin($0) }))
                    .keyboardType(.numberPad)
                    .font(.system(size: 26, weight: .semibold, design: .rounded))
                    .monospacedDigit()
                    .focused($focused)
                    .accessibilityLabel(label)
                    .accessibilityIdentifier(identifier)
                    .environment(\.layoutDirection, .leftToRight)
                Text(strings["common.label.currency_afn"])
                    .velroFont(.body)
                    .foregroundStyle(Palette.onSurfaceVariant)
            }
            .padding(.horizontal, Spacing.lg)
            .frame(minHeight: Sizing.fieldHeight + 8)
            .background(Palette.surface, in: RoundedRectangle(cornerRadius: Radius.md, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: Radius.md, style: .continuous)
                    .strokeBorder(focused ? Palette.primary : Palette.outline, lineWidth: focused ? 2 : 1)
            )
            .onTapGesture { focused = true }
        }
    }
}

/// When the journey is for, and whether it comes back.
///
/// Every journey this is for -- Ghorband to Charikar, Ghorband to Kabul -- is
/// arranged the evening before, because the car leaves at six. Days and hours
/// as chips: four taps, no keyboard, and no Hijri Shamsi calendar in a dialog.
private struct DeparturePicker: View {
    @Binding var form: AskForm
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.sm) {
            Text(strings["ride.ask.when"])
                .velroFont(.label, weight: .medium)
                .foregroundStyle(Palette.onSurface)
            FlowLayout {
                ForEach(dayChoices, id: \.key) { choice in
                    ChoiceChip(label: strings[choice.key], selected: form.departureDay == choice.day) {
                        form.setDeparture(day: choice.day, hour: form.departureHour)
                    }
                    .accessibilityIdentifier("ask.day.\(choice.day ?? -1)")
                }
            }

            // "Now" has no hour; a row of hours beside it would suggest otherwise.
            if form.departureDay != nil {
                if form.departureHours.isEmpty {
                    // Today is spent: say so rather than show an empty row.
                    Text(strings["ride.when.tomorrow"])
                        .velroFont(.caption)
                        .foregroundStyle(Palette.onSurfaceVariant)
                } else {
                    HourRow(hours: form.departureHours, selected: form.departureHour) {
                        form.setDeparture(day: form.departureDay, hour: $0)
                    }
                }

                // The way back, in the same ask: one car, one driver, one price
                // argued once. Returns are usually another day.
                Text(strings["ride.ask.return"])
                    .velroFont(.label, weight: .medium)
                    .foregroundStyle(Palette.onSurface)
                    .padding(.top, Spacing.xs)
                FlowLayout {
                    ForEach(returnChoices, id: \.label) { choice in
                        ChoiceChip(label: choice.label, selected: form.returnAfterDays == choice.after) {
                            form.setReturn(afterDays: choice.after, hour: form.returnHour)
                        }
                    }
                }

                if form.returnAfterDays != nil {
                    HourRow(hours: form.returnHours, selected: form.returnHour) {
                        form.setReturn(afterDays: form.returnAfterDays, hour: $0)
                    }
                    AmountField(label: strings["ride.ask.fare_back"], text: $form.returnFare, identifier: "ask.fare.back")
                    // Two legs argued as two numbers, added up by the app
                    // rather than by the passenger.
                    if let total = form.totalFareMinor {
                        Text(strings["ride.ask.fare_total", ["amount": MoneyFormatter.format(minor: total, currency: "AFN", strings: strings)]])
                            .velroFont(.heading, weight: .medium)
                            .foregroundStyle(Palette.onSurface)
                    }
                    Text(strings["ride.return.hint"])
                        .velroFont(.caption)
                        .foregroundStyle(Palette.onSurfaceVariant)
                }
            }
        }
    }

    private var dayChoices: [(day: Int?, key: String)] {
        [(nil, "ride.when.now"), (0, "ride.when.today"), (1, "ride.when.tomorrow"), (2, "ride.when.day_after")]
    }

    private var returnChoices: [(after: Int?, label: String)] {
        [
            (nil, strings["ride.return.none"]),
            (0, strings["ride.return.same_day"]),
            (1, strings["ride.return.next_day"]),
            (2, strings["ride.return.in_days", ["days": 2]]),
            (3, strings["ride.return.in_days", ["days": 3]]),
        ]
    }
}

/// A row of hours that opens at the chosen one: a picker that hides your own
/// choice reads as one you have not used yet.
private struct HourRow: View {
    let hours: [Int]
    let selected: Int
    let choose: (Int) -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        ScrollViewReader { reader in
            ScrollView(.horizontal) {
                HStack(spacing: Spacing.sm) {
                    ForEach(hours, id: \.self) { hour in
                        ChoiceChip(label: Numerals.localise(String(format: "%02d:00", hour), strings.locale), selected: hour == selected) {
                            choose(hour)
                        }
                        .id(hour)
                    }
                }
            }
            .scrollIndicators(.hidden)
            .onAppear { reader.scrollTo(selected, anchor: .center) }
        }
    }
}

/// The word about location, in the passenger's language before iOS speaks in
/// its own: why VELRO asks, or -- once iOS has stopped asking -- where the
/// switch is now.
struct LocationNote: View {
    let access: LocationService.Access
    let openSettings: () -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        switch access {
        case .granted:
            EmptyView()
        case .askable:
            Text(strings["location.permission.rationale"])
                .velroFont(.caption)
                .foregroundStyle(Palette.onSurfaceVariant)
        case .denied:
            VStack(alignment: .leading, spacing: Spacing.sm) {
                Text(strings["location.permission.denied"])
                    .velroFont(.caption)
                    .foregroundStyle(Palette.onSurfaceVariant)
                SecondaryButton(label: strings["location.action.open_settings"], action: openSettings)
            }
        }
    }
}
