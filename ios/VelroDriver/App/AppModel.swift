import Foundation
import Observation
import VelroCore

extension Notification.Name {
    static let velroSessionEnded = Notification.Name("af.velro.driver.session-ended")
}

/// What the whole driver app shares: the language, the session, the client,
/// and the one thing that must outlive any screen -- the trip's location
/// feed, which keeps running with the phone in his pocket.
///
/// The passenger app's AppModel, with the same members the shared screens
/// (sign-in, help, account deletion) read from it.
@MainActor
@Observable
final class AppModel {
    private(set) var locale: AppLocale
    private(set) var strings: Strings
    private(set) var isSignedIn: Bool
    /// Set the moment the account deletes itself, so the sign-in screen says
    /// it happened rather than looking like a crash.
    private(set) var accountDeleted = false

    let client: APIClient
    let store: any SessionStore
    let router = Router()
    /// His profile, earnings and trip: wiped at sign-out, because a shared
    /// handset is the normal case here.
    let personal = ResponseCache(name: "personal")
    let shared: ResponseCache
    /// The emergency numbers, kept so they work with no connection at all.
    let safety: SafetyContactsStore
    /// The car's position while he carries a trip, and the road's warnings.
    let duty: TripDuty

    private static let localeKey = "velro.locale"

    init(baseURL: URL, store: any SessionStore) {
        let locale = AppLocale(tag: UserDefaults.standard.string(forKey: Self.localeKey) ?? AppLocale.dari.tag)
        self.locale = locale
        self.strings = Strings.load(locale)
        self.store = store
        self.isSignedIn = store.accessToken != nil
        let shared = ResponseCache(name: "shared")
        self.shared = shared
        self.safety = SafetyContactsStore(cache: shared)
        let client = APIClient(baseURL: baseURL, store: store) {
            Task { @MainActor in NotificationCenter.default.post(name: .velroSessionEnded, object: nil) }
        }
        self.client = client
        self.duty = TripDuty(client: client)
        duty.strings = strings
        NotificationCenter.default.addObserver(forName: .velroSessionEnded, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.endSession() }
        }
    }

    static func live() -> AppModel {
        guard
            let raw = Bundle.main.object(forInfoDictionaryKey: "VelroAPIBaseURL") as? String,
            let url = URL(string: raw)
        else { preconditionFailure("VelroAPIBaseURL missing from Info.plist; run `make project`") }
        // Its own keychain entry: signing in to one VELRO app on a phone must
        // not sign the same person in to the other.
        let store = KeychainSessionStore(service: "af.velro.driver")
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--uitest-fresh") {
            store.clear()
            UserDefaults.standard.removeObject(forKey: localeKey)
        }
        #endif
        return AppModel(baseURL: url, store: store)
    }

    func setLocale(_ locale: AppLocale) {
        guard locale != self.locale else { return }
        UserDefaults.standard.set(locale.tag, forKey: Self.localeKey)
        self.locale = locale
        strings = Strings.load(locale)
        duty.strings = strings
        guard isSignedIn else { return }
        Task { _ = await client.send(API.updateProfile(locale: locale)) }
    }

    func signedIn(_ session: SessionDTO) {
        store.save(session)
        accountDeleted = false
        isSignedIn = true
    }

    func accountWasDeleted() {
        endSession()
        accountDeleted = true
    }

    /// The privacy page, on whichever server this build talks to.
    var privacyURL: URL {
        URL(string: "/privacy", relativeTo: client.baseURL)?.absoluteURL ?? client.baseURL
    }

    func signOut(allDevices: Bool = false) async {
        if allDevices { _ = await client.send(API.logoutAllDevices()) }
        endSession()
    }

    /// Off duty the moment nobody is signed in to be on duty for: the
    /// location feed stops with the session, not only when a screen says so.
    private func endSession() {
        duty.stop()
        personal.clear()
        store.clear()
        router.home()
        isSignedIn = false
    }
}
