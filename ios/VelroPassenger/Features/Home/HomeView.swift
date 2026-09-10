import SwiftUI
import VelroCore

/// Home, section 72: one action and what the passenger already has. A home
/// screen that tries to show everything is how a first-time user closes the app.
struct HomeView: View {
    @Environment(AppModel.self) private var app
    @Environment(\.strings) private var strings
    @State private var model: HomeModel
    @State private var helpOpen = false
    @State private var reportsAfterHelp = false

    init(app: AppModel) {
        _model = State(initialValue: HomeModel(app: app))
    }

    var body: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: 0) {
                    header(topInset: geometry.safeAreaInsets.top)

                    VStack(alignment: .leading, spacing: Spacing.md) {
                        if let open = model.openRequest {
                            OpenRequestCard(request: open) { app.router.open(.offers) }
                                .padding(.bottom, Spacing.sm)
                        }

                        HStack {
                            Text(strings["home.section.recent_trips"])
                                .velroFont(.heading)
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
                    .padding(.top, Spacing.lg)
                    .padding(.bottom, Spacing.xl)
                }
            }
            .ignoresSafeArea(edges: .top)
            .refreshable { await model.refresh() }
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

    private func header(topInset: CGFloat) -> some View {
        BrandHeader(title: strings["app.name"], topInset: topInset) {
            // In the header, so it is on screen whatever the list below is doing.
            Button { helpOpen = true } label: {
                Text(strings["safety.title"])
                    .velroFont(.label, weight: .medium)
                    .frame(minHeight: Sizing.touchTarget)
                    .contentShape(Rectangle())
            }
            .accessibilityIdentifier("home.help")
            // Her own account: also the only way to change the language once
            // signed in, so it is an icon that needs no reading.
            Button {
                app.router.open(.account)
            } label: {
                Image(systemName: "person.crop.circle.fill")
                    .font(.system(size: 26))
                    .frame(minWidth: Sizing.touchTarget, minHeight: Sizing.touchTarget)
                    .contentShape(Rectangle())
            }
            .accessibilityLabel(strings["passenger.profile.title"])
            .accessibilityIdentifier("home.account")
        } content: {
            // While a request is live the header points at it, not at a new
            // ask the server would refuse.
            Group {
                if model.openRequest != nil {
                    OnBrandButton(label: strings["home.open_request.open"], systemImage: "person.3.fill") {
                        app.router.open(.offers)
                    }
                    .accessibilityIdentifier("home.offers")
                } else {
                    OnBrandButton(label: strings["home.action.search"], systemImage: "car.fill") {
                        app.router.open(.ask)
                    }
                    .accessibilityIdentifier("home.search")
                }
            }
            .padding(.top, Spacing.lg)
        }
    }

    @ViewBuilder
    private var journeys: some View {
        if model.isLoading {
            LoadingState()
        } else if let error = model.error, model.bookings.isEmpty {
            ErrorState(error: error) { Task { await model.refresh() } }
        } else if model.bookings.isEmpty {
            // No action here: the screen's one button is already above.
            EmptyState(key: "empty.bookings", systemImage: "list.bullet.rectangle")
        } else {
            LazyVStack(spacing: Spacing.sm) {
                ForEach(model.bookings) { booking in
                    Button {
                        app.router.open(.booking(booking.id))
                    } label: {
                        BookingCard(booking: booking)
                    }
                    .buttonStyle(PressStyle())
                }
            }
        }
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
