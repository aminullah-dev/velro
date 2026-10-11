import MapKit
import SwiftUI
import VelroCore

/// Home, section 72: one action and what the passenger already has. A home
/// screen that tries to show everything is how a first-time user closes the app.
///
/// The map is the ground she stands on -- the valley, and her own dot when
/// iOS already lets VELRO see it -- with the screen's one action on a sheet
/// lying over it. Nothing on home moves under her thumb: the sheet is fixed,
/// it holds the three latest trips, and the rest are one tap away.
struct HomeView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.strings) private var strings
    @Environment(\.openURL) private var openURL
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var model: HomeModel
    @State private var helpOpen = false
    @State private var reportsAfterHelp = false
    @State private var menuOpen = false

    init(app: AppModel) {
        _model = State(initialValue: HomeModel(app: app))
    }

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .top) {
                if geometry.size.width >= Wide.threshold {
                    // Unfolded: the whole screen is map, and the sheet stands
                    // beside it as a panel rather than stretching across.
                    HomeMap().ignoresSafeArea()
                    HStack(alignment: .top, spacing: 0) {
                        FixedSheet {
                            sheetContent.padding(.top, Spacing.lg)
                        }
                        .frame(width: Wide.panel)
                        .floatingPanel()
                        Spacer(minLength: 0)
                    }
                    .padding(.leading, Spacing.gutter)
                    .padding(.top, Sizing.touchTarget + Spacing.lg)
                    .padding(.bottom, Spacing.lg)
                } else {
                    HomeMap().ignoresSafeArea()

                    VStack(spacing: 0) {
                        Spacer(minLength: 0)
                        FixedSheet {
                            sheetContent.padding(.top, Spacing.xl)
                        }
                        .frame(height: geometry.size.height * 0.58)
                        .sheetPanel()
                    }
                }

                topBar
                    .padding(.horizontal, Spacing.gutter)
                    .padding(.top, Spacing.xs)

                if menuOpen {
                    SideMenu(close: closeMenu, open: openFromMenu)
                        .zIndex(1)
                }
            }
        }
        .background(Palette.background)
        .toolbar(.hidden, for: .navigationBar)
        // Every return to home, not only the first: back from the offers or a
        // booking, the card and the list must say what just happened.
        .onAppear { Task { await model.refresh() } }
        .task { await model.poll() }
        // Help on home, where she is when she is not mid-journey: a woman
        // harassed during a ride must still be able to tell VELRO once she is
        // out of the car.
        .sheet(isPresented: $helpOpen, onDismiss: openReportsIfAsked) {
            HelpSheet(app: app, ride: nil, openReports: { reportsAfterHelp = true })
        }
    }

    private func openReportsIfAsked() {
        guard reportsAfterHelp else { return }
        reportsAfterHelp = false
        app.router.open(.reports)
    }

    private func closeMenu() {
        withAnimation(reduceMotion ? nil : .snappy(duration: 0.28)) { menuOpen = false }
    }

    private func openFromMenu(_ item: SideMenu.Item) {
        closeMenu()
        switch item {
        case .account: app.router.open(.account)
        case .history: app.router.open(.history)
        case .help: helpOpen = true
        case .reports: app.router.open(.reports)
        case .privacy: openURL(app.privacyURL)
        }
    }

    /// Round buttons floating on the map: the menu at the start; help and
    /// her account at the end, on screen whatever the sheet is doing.
    private var topBar: some View {
        HStack(spacing: Spacing.sm) {
            RoundIconButton(systemImage: "line.3.horizontal", label: strings["common.action.menu"]) {
                withAnimation(reduceMotion ? nil : .snappy(duration: 0.32)) { menuOpen = true }
            }
            .accessibilityIdentifier("home.menu")
            Spacer()
            Button { helpOpen = true } label: {
                Label {
                    Text(strings["safety.title"]).velroFont(.label, weight: .bold)
                } icon: {
                    Image(systemName: "shield.lefthalf.filled")
                }
                .foregroundStyle(Palette.brandField)
                .padding(.horizontal, Spacing.lg)
                .frame(minHeight: Sizing.touchTarget)
                .glass(in: Capsule())
                .contentShape(Capsule())
            }
            .buttonStyle(PressStyle())
            .accessibilityIdentifier("home.help")
            // Her own account: also the only way to change the language once
            // signed in, so it is an icon that needs no reading.
            RoundIconButton(systemImage: "person.fill", label: strings["passenger.profile.title"]) {
                app.router.open(.account)
            }
            .accessibilityIdentifier("home.account")
        }
    }

    private var sheetContent: some View {
        VStack(alignment: .leading, spacing: Spacing.md) {
            // While a request is live the sheet points at it, not at a new
            // ask the server would refuse.
            if let open = model.openRequest {
                PrimaryButton(label: strings["home.open_request.open"]) { app.router.open(.offers) }
                    .accessibilityIdentifier("home.offers")
                    .padding(.top, Spacing.sm)
                OpenRequestCard(request: open) { app.router.open(.offers) }
                    .padding(.bottom, Spacing.sm)
            } else {
                WhereToBar { app.router.open(.ask) }
                    .padding(.top, Spacing.sm)
                    .padding(.bottom, Spacing.sm)
            }

            HStack {
                Text(strings["home.section.recent_trips"])
                    .velroFont(.heading, weight: .bold)
                    .foregroundStyle(Palette.onSurface)
                Spacer()
                // Home shows the few most recent; the rest, and the
                // receipts, live behind this.
                TextAction(label: strings["history.title"]) { app.router.open(.history) }
                    .accessibilityIdentifier("home.history")
            }

            // Saved data, honestly labelled.
            if model.isStale && !model.bookings.isEmpty {
                Text(strings["common.state.offline"])
                    .velroFont(.caption)
                    .foregroundStyle(Palette.onSurfaceVariant)
            }

            journeys
        }
        .padding(.horizontal, Spacing.gutter)
        .padding(.bottom, Spacing.xxl)
    }

    @ViewBuilder
    private var journeys: some View {
        if model.isLoading {
            ProgressView()
                .tint(Palette.primary)
                .frame(maxWidth: .infinity, minHeight: 96)
        } else if let error = model.error, model.bookings.isEmpty {
            ErrorState(error: error) { Task { await model.refresh() } }
        } else if model.bookings.isEmpty {
            // No action here: the screen's one button is already above.
            Label {
                Text(strings["empty.bookings"]).velroFont(.label)
            } icon: {
                Image(systemName: "list.bullet.rectangle")
            }
            .foregroundStyle(Palette.onSurfaceVariant)
            .frame(maxWidth: .infinity, minHeight: 72)
        } else {
            VStack(spacing: 0) {
                // The three latest: as many as fit without the sheet having
                // to scroll. The rest, and the receipts, are behind "trips".
                ForEach(Array(model.bookings.prefix(3).enumerated()), id: \.element.id) { index, booking in
                    if index > 0 { Divider().padding(.leading, 40 + Spacing.md) }
                    Button {
                        app.router.open(.booking(booking.id))
                    } label: {
                        BookingRow(booking: booking)
                    }
                    .buttonStyle(PressStyle())
                }
            }
        }
    }
}

/// The sheet's contents, still: it scrolls only when they genuinely do not
/// fit -- the largest text size on the smallest phone -- and otherwise sits
/// as fixed as the map under it.
private struct FixedSheet<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        ScrollView {
            content
        }
        .scrollIndicators(.hidden)
        .scrollBounceBehavior(.basedOnSize)
    }
}

/// The valley under the sheet: Apple's map, muted, so the sheet and its one
/// action stay the loudest thing on screen. Her own position only when iOS
/// already allows it -- home never asks; the ask does, and says why first.
private struct HomeMap: View {
    @State private var position: MapCameraPosition = .region(MKCoordinateRegion(
        // Ghorband, where the service runs.
        center: CLLocationCoordinate2D(latitude: 34.955, longitude: 68.62),
        span: MKCoordinateSpan(latitudeDelta: 0.09, longitudeDelta: 0.09)
    ))
    @State private var located = false

    var body: some View {
        Map(position: $position, interactionModes: []) {
            if located { UserAnnotation() }
        }
        .mapStyle(.standard(emphasis: .muted, pointsOfInterest: .excludingAll))
        // A wash at the top so the status bar and the round buttons read on
        // any tile.
        .overlay(alignment: .top) {
            LinearGradient(colors: [Palette.background.opacity(0.6), .clear], startPoint: .top, endPoint: .bottom)
                .frame(height: 110)
                .allowsHitTesting(false)
        }
        .accessibilityHidden(true)
        .onAppear {
            let status = CLLocationManager().authorizationStatus
            if status == .authorizedWhenInUse || status == .authorizedAlways {
                located = true
                position = .userLocation(fallback: position)
            }
        }
    }
}

/// The menu behind the round button: where everything that is not the
/// screen's one action lives. Slides from the start edge, over a dimmed map;
/// a tap outside, the close button, or the escape gesture puts it away.
struct SideMenu: View {
    enum Item: CaseIterable {
        case account, history, help, reports, privacy

        var labelKey: String {
            switch self {
            case .account: "passenger.profile.title"
            case .history: "history.title"
            case .help: "safety.title"
            case .reports: "safety.my_reports"
            case .privacy: "account.privacy"
            }
        }

        var systemImage: String {
            switch self {
            case .account: "person.crop.circle.fill"
            case .history: "clock.arrow.circlepath"
            case .help: "shield.lefthalf.filled"
            case .reports: "doc.text.fill"
            case .privacy: "lock.fill"
            }
        }
    }

    let close: () -> Void
    let open: (Item) -> Void
    @Environment(\.strings) private var strings
    @Environment(\.layoutDirection) private var direction
    @State private var shown = false

    var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .leading) {
                Color.black.opacity(shown ? 0.35 : 0)
                    .ignoresSafeArea()
                    .onTapGesture(perform: close)
                    .accessibilityHidden(true)

                panel
                    .frame(width: min(geometry.size.width * 0.82, 360))
                    .frame(maxHeight: .infinity)
                    .background(
                        UnevenRoundedRectangle(bottomTrailingRadius: Radius.sheet, topTrailingRadius: Radius.sheet, style: .continuous)
                            .fill(Palette.surface.opacity(0.86))
                            .background(.regularMaterial, in: UnevenRoundedRectangle(bottomTrailingRadius: Radius.sheet, topTrailingRadius: Radius.sheet, style: .continuous))
                            .ignoresSafeArea()
                            .elevation(.high)
                    )
                    // An offset is not mirrored with the layout: in Dari the
                    // start edge is the right, so the panel comes from there.
                    .offset(x: shown ? 0 : (direction == .rightToLeft ? geometry.size.width : -geometry.size.width))
            }
        }
        .transition(.opacity)
        .onAppear { withAnimation(.snappy(duration: 0.32)) { shown = true } }
        .accessibilityAddTraits(.isModal)
        .accessibilityAction(.escape, close)
    }

    private var panel: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button(action: close) {
                Image(systemName: "xmark")
                    .font(.system(size: 20, weight: .semibold))
                    .foregroundStyle(Palette.brandField)
                    .frame(width: Sizing.touchTarget, height: Sizing.touchTarget)
                    .contentShape(Rectangle())
            }
            .buttonStyle(PressStyle())
            .accessibilityLabel(strings["common.action.close"])
            .accessibilityIdentifier("menu.close")
            .padding(.leading, Spacing.sm)

            VStack(alignment: .leading, spacing: Spacing.xxs) {
                Text(strings["app.name"])
                    .velroFont(.display)
                    .foregroundStyle(Palette.primary)
                Text(strings["app.tagline"])
                    .velroFont(.caption)
                    .foregroundStyle(Palette.onSurfaceVariant)
            }
            .padding(.horizontal, Spacing.gutter)
            .padding(.top, Spacing.lg)
            .padding(.bottom, Spacing.xxl)
            .accessibilityElement(children: .combine)

            ForEach(Item.allCases, id: \.self) { item in
                Button { open(item) } label: {
                    HStack(spacing: Spacing.lg) {
                        Image(systemName: item.systemImage)
                            .font(.system(size: 18, weight: .semibold))
                            .foregroundStyle(Palette.primary)
                            .frame(width: 40, height: 40)
                            .background(Palette.primaryContainer, in: Circle())
                            .accessibilityHidden(true)
                        Text(strings[item.labelKey])
                            .velroFont(.body, weight: .medium)
                            .foregroundStyle(Palette.onSurface)
                        Spacer(minLength: Spacing.sm)
                        Image(systemName: "chevron.forward")
                            .font(.footnote.weight(.semibold))
                            .foregroundStyle(Palette.outline)
                            .accessibilityHidden(true)
                    }
                    .padding(.horizontal, Spacing.gutter)
                    .frame(minHeight: 64)
                    .contentShape(Rectangle())
                }
                .buttonStyle(PressStyle())
                .accessibilityIdentifier("menu.\(item)")
                Divider().padding(.leading, Spacing.gutter + 40 + Spacing.lg)
            }
            Spacer()
        }
        .padding(.top, Spacing.sm)
    }
}

/// Her open ask, with a clock on it. Without a visible deadline the only two
/// states she can tell apart are "something is happening" and "nothing is",
/// which look the same.
private struct OpenRequestCard: View {
    let request: RideRequest
    let open: () -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.xs) {
                Text(strings["home.open_request.title"])
                    .velroFont(.heading, weight: .medium)
                    .foregroundStyle(Palette.onSurface)
                let offers = request.liveOffers.count
                Text(offers > 0
                     ? strings["home.open_request.offers", ["count": offers]]
                     : strings["home.open_request.waiting"])
                    .velroFont(.label)
                    .foregroundStyle(Palette.onSurface)
                if let deadline = request.expiry {
                    // Recomputed against the clock, so it cannot show a number
                    // that stopped being true while the app was away.
                    TimelineView(.periodic(from: .now, by: 20)) { context in
                        let minutes = Calendars.minutesUntil(deadline, now: context.date)
                        Text(minutes >= 1
                             ? strings["home.open_request.expires_in", ["minutes": minutes]]
                             : strings["home.open_request.expiring"])
                            .velroFont(.caption)
                            .foregroundStyle(Palette.onSurfaceVariant)
                    }
                }
                // Secondary: the header already carries this destination as
                // the screen's one primary action.
                SecondaryButton(label: strings["home.open_request.open"], action: open)
                    .padding(.top, Spacing.sm)
            }
        }
    }
}

/// "Where to?" -- the bar every ride app she may have used opens on.
///
/// Shaped like a search field because that is what it is to her: tap, and say
/// where. The line under it says the flow begins where she is standing, so the
/// first thing she sees after the tap -- her own position already found -- is
/// what she was told would happen. Still one action, still the header's.
private struct WhereToBar: View {
    let action: () -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.sm) {
            Button(action: action) {
                HStack(spacing: Spacing.md) {
                    Image(systemName: "magnifyingglass")
                        .font(.system(size: 22, weight: .semibold))
                        .foregroundStyle(Palette.outline)
                        .accessibilityHidden(true)
                    Text(strings["home.search.where_to"])
                        .velroFont(.title, weight: .medium)
                        .foregroundStyle(Palette.onSurface)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                    Spacer()
                    Image(systemName: "car.fill")
                        .font(.system(size: 18, weight: .semibold))
                        .foregroundStyle(Palette.onPrimary)
                        .frame(width: 48, height: 48)
                        .background(Palette.primary, in: Circle())
                        .accessibilityHidden(true)
                }
                .padding(.leading, Spacing.xl - Spacing.xs)
                .padding(.trailing, Spacing.sm)
                .frame(maxWidth: .infinity, minHeight: 64)
                .background(Palette.surface, in: Capsule())
                .elevation(.low)
                .contentShape(Capsule())
            }
            .buttonStyle(PressStyle())
            .accessibilityIdentifier("home.search")

            Label {
                Text(strings["home.search.from_here"]).velroFont(.caption)
            } icon: {
                Image(systemName: "location.fill").font(.caption)
            }
            .foregroundStyle(Palette.onSurfaceVariant)
            .padding(.leading, Spacing.lg)
            .accessibilityHidden(true)
        }
    }
}
