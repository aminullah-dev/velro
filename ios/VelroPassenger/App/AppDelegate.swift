import SwiftUI
import UIKit

@main
final class AppDelegate: UIResponder, UIApplicationDelegate {
    /// Upright on a phone, where the app is used one-handed in a moving car
    /// and a turn of the wrist must not throw the screen sideways. On a
    /// screen big enough to be held like a book -- an unfolded iPhone Duo --
    /// any way up but upside down, where the app's Info.plist allows it (the
    /// driver's does not).
    func application(_ application: UIApplication, supportedInterfaceOrientationsFor window: UIWindow?) -> UIInterfaceOrientationMask {
        #if DEBUG
        // The wide layout, checked on a phone turned on its side: there is no
        // simulator of an unfolded Duo to check it on.
        if ProcessInfo.processInfo.arguments.contains("--uitest-any-orientation") { return .allButUpsideDown }
        #endif
        guard let screen = window?.windowScene?.screen else { return .portrait }
        let declared = Bundle.main.object(forInfoDictionaryKey: "UISupportedInterfaceOrientations") as? [String] ?? []
        let bookSized = min(screen.bounds.width, screen.bounds.height) >= 600
        return bookSized && declared.count > 1 ? .allButUpsideDown : .portrait
    }
}

/// The window, hosted by UIKit rather than by a SwiftUI `App`.
///
/// For one reason: the status bar. Sign-in and home open on the brand green,
/// where dark status-bar icons measure 2.7:1, and SwiftUI offers no way to
/// set the style for a screen without a visible navigation bar. A hosting
/// controller can -- see `BrandStatusBar`.
final class SceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?
    private let app = AppModel.live()

    func scene(
        _ scene: UIScene,
        willConnectTo session: UISceneSession,
        options connectionOptions: UIScene.ConnectionOptions
    ) {
        guard let windowScene = scene as? UIWindowScene else { return }
        let window = UIWindow(windowScene: windowScene)
        let host = StatusBarHostingController(rootView: AnyView(EmptyView()))
        host.rootView = AnyView(
            RootView()
                .environment(app)
                .onPreferenceChange(BrandStatusBar.self) { onBrand in
                    MainActor.assumeIsolated { host.isOnBrandField = onBrand }
                }
        )
        window.rootViewController = host
        window.makeKeyAndVisible()
        self.window = window
    }
}

final class StatusBarHostingController: UIHostingController<AnyView> {
    var isOnBrandField = false {
        didSet { if oldValue != isOnBrandField { setNeedsStatusBarAppearanceUpdate() } }
    }

    override var preferredStatusBarStyle: UIStatusBarStyle {
        isOnBrandField ? .lightContent : .default
    }
}

/// Set by a screen whose top is the brand field, so the status bar above it
/// turns light -- and back when the screen goes.
struct BrandStatusBar: PreferenceKey {
    static let defaultValue = false
    static func reduce(value: inout Bool, nextValue: () -> Bool) { value = value || nextValue() }
}
