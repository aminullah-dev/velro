import Foundation
import Observation
import VelroCore

extension Notification.Name {
    static let velroSessionEnded = Notification.Name("af.velro.session-ended")
}

/// What the whole app shares: the language, the session and the client.
@MainActor
@Observable
final class AppModel {
    private(set) var locale: AppLocale
    private(set) var strings: Strings
    private(set) var isSignedIn: Bool
    /// Set the moment the account deletes itself, so the sign-in screen she
    /// lands on says it happened rather than looking like a crash; cleared by
    /// the next sign-in.
    private(set) var accountDeleted = false

    let client: APIClient
    let store: any SessionStore
    let router = Router()
    /// This person's journeys, requests and reports: wiped at sign-out,
    /// because a shared handset is the normal case here.
    let personal = ResponseCache(name: "personal")
    /// The places, which belong to nobody and survive a sign-out.
    let shared: ResponseCache
    /// The emergency numbers, kept so they work with no connection at all.
    let safety: SafetyContactsStore
    let geography: GeographyStore

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
        self.geography = GeographyStore(cache: shared)
        // The client hears that the server refused to renew the session; the
        // app hears it from the client, and the screen becomes sign-in again.
        self.client = APIClient(baseURL: baseURL, store: store) {
            Task { @MainActor in NotificationCenter.default.post(name: .velroSessionEnded, object: nil) }
        }
        NotificationCenter.default.addObserver(forName: .velroSessionEnded, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.endSession() }
        }
    }

    static func live() -> AppModel {
        guard
            let raw = Bundle.main.object(forInfoDictionaryKey: "VelroAPIBaseURL") as? String,
            let url = URL(string: raw)
        else { preconditionFailure("VelroAPIBaseURL missing from Info.plist; run `make project`") }
        let store = KeychainSessionStore(service: "af.velro.passenger")
        #if DEBUG
        // The UI tests start every run signed out, in Dari. Debug builds only:
        // a shipped app has no argument that throws a session away.
        if ProcessInfo.processInfo.arguments.contains("--uitest-fresh") {
            store.clear()
            UserDefaults.standard.removeObject(forKey: localeKey)
        }
        #endif
        return AppModel(baseURL: url, store: store)
    }

    /// Change the language. Stored here first, because that is what the app
    /// reads; the account is told so the next SMS arrives in it too, and a
    /// failure there is caught up on the next successful write.
    func setLocale(_ locale: AppLocale) {
        guard locale != self.locale else { return }
        UserDefaults.standard.set(locale.tag, forKey: Self.localeKey)
        self.locale = locale
        strings = Strings.load(locale)
        guard isSignedIn else { return }
        Task { _ = await client.send(API.updateProfile(locale: locale)) }
    }

    func signedIn(_ session: SessionDTO) {
        store.save(session)
        accountDeleted = false
        isSignedIn = true
    }

    /// The server has already revoked every session, so there is nobody to
    /// tell: the phone forgets the account exactly as a sign-out does.
    func accountWasDeleted() {
        endSession()
        accountDeleted = true
    }

    /// The privacy page, on whichever server this build talks to: it lives at
    /// the host's root, beside the download page, not under the API.
    var privacyURL: URL {
        URL(string: "/privacy", relativeTo: client.baseURL)?.absoluteURL ?? client.baseURL
    }

    /// Sign out. The saved journeys go first: if anything fails after that,
    /// the worst case is an app that still looks signed in -- a confusion,
    /// not the last person's trips left on a shared phone.
    func signOut(allDevices: Bool = false) async {
        if allDevices { _ = await client.send(API.logoutAllDevices()) }
        endSession()
    }

    private func endSession() {
        personal.clear()
        store.clear()
        router.home()
        isSignedIn = false
    }
}
