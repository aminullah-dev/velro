import Foundation
import Observation
import VelroCore
import WidgetKit

extension Notification.Name {
    static let velroWatchSessionEnded = Notification.Name("af.velro.ops.watch.session-ended")
}

/// Everything the watch knows: the language, the session and the last
/// dashboard it read.
///
/// For glancing, not for work: it reads `admin/dashboard` and nothing else,
/// and hands the attention figures to the complications after every read.
@MainActor
@Observable
final class WatchModel {
    private(set) var locale: AppLocale {
        didSet { if locale != oldValue { applyLocale() } }
    }
    private(set) var strings: Strings
    private(set) var isSignedIn: Bool
    /// An error code the signed-out screen explains: PERMISSION_DENIED when a
    /// session turned out to have no staff role.
    private(set) var signOutReason: String?
    /// The last dashboard read -- kept, and shown with its age, when a
    /// refresh fails.
    private(set) var snapshot: DashboardSnapshot?
    /// When `snapshot` arrived on this watch.
    private(set) var fetchedAt: Date?
    /// Why the last refresh failed; nil after one that worked.
    private(set) var lastError: APIError?
    private(set) var isRefreshing = false
    /// The server said 403: a staff role without the dashboard.
    private(set) var noDashboard = false

    let client: APIClient
    let store: WatchSessionStore
    /// The dashboard's last answer on disk, so the watch opens on figures
    /// (labelled with their age) even with no connection.
    private let cache = ResponseCache(name: "watch-session")

    private static let dashboardKey = "dashboard"
    private static let localeKey = "velro-ops-watch-locale"
    /// Set once a language is picked on the watch; until then the account's
    /// own language (auth/me) is followed.
    private static let localeChosenKey = "velro-ops-watch-locale-chosen"
    private static let fetchedKey = "velro-ops-watch-fetched-at"

    init(baseURL: URL, store: WatchSessionStore) {
        let defaults = UserDefaults.standard
        let locale = AppLocale(tag: defaults.string(forKey: Self.localeKey) ?? AppLocale.dari.tag)
        self.locale = locale
        self.strings = Strings.load(locale)
        self.store = store
        let signedIn = store.accessToken != nil
        self.isSignedIn = signedIn
        self.client = APIClient(baseURL: baseURL, store: store) {
            Task { @MainActor in NotificationCenter.default.post(name: .velroWatchSessionEnded, object: nil) }
        }
        if signedIn {
            snapshot = cache.value(DashboardSnapshot.self, key: Self.dashboardKey)
            fetchedAt = defaults.object(forKey: Self.fetchedKey) as? Date
        }
        NotificationCenter.default.addObserver(forName: .velroWatchSessionEnded, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.endSession(reason: nil) }
        }
        publishPrefs()
    }

    static func live() -> WatchModel {
        guard
            let raw = Bundle.main.object(forInfoDictionaryKey: "VelroAPIBaseURL") as? String,
            let url = URL(string: raw)
        else { preconditionFailure("VelroAPIBaseURL missing from Info.plist; run `make project`") }
        // Its own entry, apart from the phone's `af.velro.ops`: two devices,
        // two sessions, two refresh tokens that never meet.
        return WatchModel(baseURL: url, store: WatchSessionStore(service: "af.velro.ops.watch"))
    }

    // MARK: What is shown

    /// When the figures on screen were true.
    var asOf: Date? { snapshot?.generated ?? fetchedAt }

    var summary: AttentionSummary? {
        snapshot.map { AttentionSummary(snapshot: $0, fetchedAt: fetchedAt ?? .now) }
    }

    // MARK: Language

    /// A language picked on the watch, which then stays, whatever the
    /// account's own is.
    func choose(_ locale: AppLocale) {
        UserDefaults.standard.set(true, forKey: Self.localeChosenKey)
        self.locale = locale
    }

    private func applyLocale() {
        UserDefaults.standard.set(locale.tag, forKey: Self.localeKey)
        strings = Strings.load(locale)
        publishPrefs()
        WidgetCenter.shared.reloadAllTimelines()
    }

    // MARK: The session

    /// A verified code. Refused -- and not saved -- for an account with no
    /// staff role: its code is valid, it simply opens nothing here.
    @discardableResult
    func signedIn(_ session: SessionDTO) -> Bool {
        guard StaffAccess.isStaff(session.roles) else {
            signOutReason = "PERMISSION_DENIED"
            return false
        }
        store.save(session)
        signOutReason = nil
        noDashboard = false
        isSignedIn = true
        publishPrefs()
        return true
    }

    func clearSignOutReason() { signOutReason = nil }

    /// Who this is: signs out a session whose staff role was taken away, and
    /// follows the account's language until one is picked on the watch. A
    /// failed request proves nothing and changes nothing.
    func recheckProfile() async {
        guard isSignedIn, case .success(let me) = await client.send(API.profile()), isSignedIn else { return }
        guard StaffAccess.isStaff(me.roles) else {
            endSession(reason: "PERMISSION_DENIED")
            return
        }
        if !UserDefaults.standard.bool(forKey: Self.localeChosenKey) {
            locale = AppLocale(tag: me.locale)
        }
    }

    /// Sign out of this watch. The phone's session is another one and stays.
    func signOut() {
        endSession(reason: nil)
    }

    private func endSession(reason: String?) {
        store.clear()
        cache.clear()
        UserDefaults.standard.removeObject(forKey: Self.fetchedKey)
        snapshot = nil
        fetchedAt = nil
        lastError = nil
        noDashboard = false
        isSignedIn = false
        signOutReason = reason
        SharedVault.delete(.summary)
        publishPrefs()
        WidgetCenter.shared.reloadAllTimelines()
    }

    // MARK: The dashboard

    /// Read the dashboard again. A failure keeps the figures already shown;
    /// the screen says how old they are.
    func refresh() async {
        guard isSignedIn, !isRefreshing else { return }
        isRefreshing = true
        defer { isRefreshing = false }
        let result = await client.send(AdminAPI.dashboard(), caching: Self.dashboardKey, in: cache)
        guard isSignedIn else { return }
        if let error = result.error {
            guard error != .cancelled else { return }
            lastError = error
            if snapshot == nil { snapshot = result.value }
            if error.httpStatus == 403 {
                noDashboard = true
                // A role taken away mid-session is noticed here.
                await recheckProfile()
            }
            return
        }
        guard let value = result.value else { return }
        let now = Date()
        snapshot = value
        fetchedAt = now
        lastError = nil
        noDashboard = false
        UserDefaults.standard.set(now, forKey: Self.fetchedKey)
        SharedVault.write(AttentionSummary(snapshot: value, fetchedAt: now), .summary)
        // In the foreground, so it costs the complications' budget nothing.
        WidgetCenter.shared.reloadAllTimelines()
    }

    private func publishPrefs() {
        SharedVault.write(WatchPrefs(locale: locale.tag, signedIn: isSignedIn), .prefs)
    }
}
