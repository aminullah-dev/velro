import SwiftUI
import VelroCore

extension EnvironmentValues {
    /// The text in the chosen language. Every screen reads its words from here.
    @Entry var strings = Strings(locale: .dari, translations: [:], fallback: [:])
}

/// Sign-in or the signed-in app, in the chosen language and direction.
struct RootView: View {
    @Environment(AppModel.self) private var app

    var body: some View {
        Group {
            if app.isSignedIn {
                SignedInView(app: app)
            } else {
                SignInView(app: app)
            }
        }
        // Direction follows the chosen language, not the phone's setting.
        .environment(\.layoutDirection, app.locale.isRTL ? .rightToLeft : .leftToRight)
        .environment(\.locale, Locale(identifier: app.locale.tag))
        .environment(\.strings, app.strings)
        .tint(Palette.primary)
        .animation(.default, value: app.isSignedIn)
        // The numbers to dial are fetched whenever there is a connection, so
        // they are already on the phone when they are needed.
        .task { await app.safety.refresh(using: app.client) }
    }
}

private struct SignedInView: View {
    @Bindable private var router: Router
    private let app: AppModel

    init(app: AppModel) {
        self.app = app
        router = app.router
    }

    var body: some View {
        NavigationStack(path: $router.path) {
            HomeView(app: app)
                .navigationDestination(for: Route.self) { route in
                    destination(route)
                }
        }
    }

    @ViewBuilder
    private func destination(_ route: Route) -> some View {
        switch route {
        case .ask: AskView(app: app)
        case .offers: OffersView(app: app)
        case .booking(let id): BookingDetailView(app: app, bookingId: id)
        case .track(let id): TrackRideView(app: app, bookingId: id)
        case .history: HistoryView(app: app)
        case .account: AccountView(app: app)
        case .deleteAccount: DeleteAccountView(app: app)
        case .reports: ReportsView(app: app)
        }
    }
}
