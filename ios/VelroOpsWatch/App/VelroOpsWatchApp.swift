import SwiftUI
import VelroCore

/// VELRO Ops on the wrist: what needs somebody right now, at a glance.
///
/// A single-target watchOS app, embedded in VELRO Ops for iPhone and
/// signed in on its own (see `WatchSessionStore` for why).
@main
struct VelroOpsWatchApp: App {
    @State private var model = WatchModel.live()

    var body: some Scene {
        WindowGroup {
            WatchRoot()
                .environment(model)
        }
    }
}

/// Signed out or the dashboard, in the chosen language and direction, read
/// again every minute while the app is on screen.
struct WatchRoot: View {
    @Environment(WatchModel.self) private var model
    @Environment(\.scenePhase) private var scenePhase

    private struct Cycle: Hashable {
        let active: Bool
        let signedIn: Bool
    }

    var body: some View {
        Group {
            if model.isSignedIn {
                DashboardView()
            } else {
                SignedOutView()
            }
        }
        // Direction follows the chosen language, not the watch's setting.
        .environment(\.layoutDirection, model.locale.isRTL ? .rightToLeft : .leftToRight)
        .environment(\.locale, Locale(identifier: model.locale.tag))
        .tint(WatchPalette.amber)
        .task(id: Cycle(active: scenePhase == .active, signedIn: model.isSignedIn)) { [model, scenePhase] in
            guard scenePhase == .active, model.isSignedIn else { return }
            await model.recheckProfile()
            while !Task.isCancelled {
                await model.refresh()
                try? await Task.sleep(for: .seconds(60))
            }
        }
    }
}
