import Foundation
import Observation
import VelroCore

extension Notification.Name {
    static let velroOpsSessionEnded = Notification.Name("af.velro.ops.session-ended")
}

/// What the whole console shares: the language, the session, the client, who
/// is signed in and what their roles open.
///
/// Feature screens read it with `@Environment(OpsModel.self)` and call the
/// API through `send` / `sendWithMeta` / `download` rather than `client`
/// directly, so the shell's offline banner knows when the server went away.
@MainActor
@Observable
final class OpsModel {
    /// The language being read. Set it and the whole console changes, and the
    /// account's own locale follows on the server.
    var locale: AppLocale {
        didSet { if locale != oldValue { applyLocale() } }
    }
    private(set) var strings: Strings
    private(set) var isSignedIn: Bool
    /// The signed-in account, from `auth/me`. Nil until the first check.
    private(set) var profile: ProfileDTO?
    /// The account's roles. Kept on the device between launches so the
    /// console opens without a connection; re-checked whenever there is one.
    private(set) var roles: [String]
    /// An error code the sign-in screen explains: PERMISSION_DENIED when a
    /// session turned out to have no staff role.
    private(set) var signOutReason: String?
    /// The last call could not reach the server.
    private(set) var isOffline = false
    /// The dashboard's "needs attention" counts, for the sidebar's badges.
    private(set) var attention: DashboardSnapshot.Attention?
    private(set) var settlementsOpen: Int?

    let client: APIClient
    let store: any SessionStore
    let navigator = OpsNavigator()

    private static let localeKey = "velro.ops.locale"
    private static let rolesKey = "velro.ops.roles"

    init(baseURL: URL, store: any SessionStore) {
        let locale = AppLocale(tag: UserDefaults.standard.string(forKey: Self.localeKey) ?? AppLocale.dari.tag)
        self.locale = locale
        self.strings = Strings.load(locale)
        self.store = store
        let signedIn = store.accessToken != nil
        self.isSignedIn = signedIn
        self.roles = signedIn ? (UserDefaults.standard.stringArray(forKey: Self.rolesKey) ?? []) : []
        self.client = APIClient(baseURL: baseURL, store: store) {
            Task { @MainActor in NotificationCenter.default.post(name: .velroOpsSessionEnded, object: nil) }
        }
        navigator.reset(for: StaffAccess(roles: roles))
        // Asked live, so a role changed mid-session counts from then on.
        navigator.canOpen = { [weak self] route in self?.can(route) ?? false }
        #if DEBUG
        // Screenshots of each screen without tapping: a development build
        // opens the screen its launch arguments name (-VelroOpsRoute dashboard).
        if let raw = UserDefaults.standard.string(forKey: "VelroOpsRoute"),
           let route = Route(rawValue: raw), can(route) {
            navigator.open(route)
        }
        #endif
        NotificationCenter.default.addObserver(forName: .velroOpsSessionEnded, object: nil, queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.endSession(reason: nil) }
        }
    }

    static func live() -> OpsModel {
        guard
            let raw = Bundle.main.object(forInfoDictionaryKey: "VelroAPIBaseURL") as? String,
            let url = URL(string: raw)
        else { preconditionFailure("VelroAPIBaseURL missing from Info.plist; run `make project`") }
        // Its own keychain entry: signing in to a passenger or driver app on
        // the same device must not sign anybody in here, or the reverse.
        let store = KeychainSessionStore(service: "af.velro.ops")
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--uitest-fresh") {
            store.clear()
            UserDefaults.standard.removeObject(forKey: localeKey)
            UserDefaults.standard.removeObject(forKey: rolesKey)
        }
        #endif
        return OpsModel(baseURL: url, store: store)
    }

    // MARK: Who may do what

    var access: StaffAccess { StaffAccess(roles: roles) }
    /// Dispatch, the live map, approvals, users, live requests.
    var isOperations: Bool { access.isOperations }
    /// Payouts, debtors, the finance summary.
    var isFinance: Bool { access.isFinance }
    /// The support queue.
    var isSupport: Bool { access.isSupport }
    /// The audit log.
    var isAdmin: Bool { access.isAdmin }

    func can(_ route: Route) -> Bool { route.isAllowed(for: access) }

    /// The routes this account's roles open, in the sidebar's order.
    var visibleRoutes: [Route] { Route.allCases.filter { can($0) } }

    // MARK: The API

    /// The call, noting whether the server could be reached.
    func send<T>(_ endpoint: Endpoint<T>) async -> Result<T, APIError> {
        let result = await client.send(endpoint)
        note(result)
        return result
    }

    /// The call, with the envelope's meta: a list's total, the dispatch
    /// board's counts.
    func sendWithMeta<T>(_ endpoint: Endpoint<T>) async -> Result<Paged<T>, APIError> {
        let result = await client.sendWithMeta(endpoint)
        note(result)
        return result
    }

    /// A document's bytes, with the bearer token. Held in memory only.
    func download(_ endpoint: Endpoint<DownloadedFile>) async -> Result<DownloadedFile, APIError> {
        let result = await client.download(endpoint)
        note(result)
        return result
    }

    private func note<T>(_ result: Result<T, APIError>) {
        switch result {
        case .success:
            isOffline = false
        case .failure(let error):
            if error.code == APIError.offlineCode {
                isOffline = true
            } else if error.httpStatus > 0 {
                isOffline = false
            }
        }
    }

    // MARK: The session

    /// A verified code. Refused -- and not saved -- for an account with no
    /// staff role: its credentials are valid, it simply has no business here.
    @discardableResult
    func signedIn(_ session: SessionDTO) -> Bool {
        guard StaffAccess.isStaff(session.roles) else {
            signOutReason = "PERMISSION_DENIED"
            return false
        }
        store.save(session)
        adopt(roles: session.roles)
        signOutReason = nil
        isSignedIn = true
        navigator.reset(for: access)
        return true
    }

    /// Ask the server who this is, and sign out a session whose staff role
    /// was taken away.
    ///
    /// The refresh token outlives a role -- the account is still a valid
    /// passenger -- so without this a demoted operator would keep every
    /// screen and a 403 on each (admin/src/api/roles.ts). A failed request
    /// proves nothing about roles and signs nobody out; it comes back so a
    /// screen with nothing to show yet can say why.
    @discardableResult
    func recheckStaff() async -> APIError? {
        guard isSignedIn else { return nil }
        switch await send(API.profile()) {
        case .failure(let error):
            return error
        case .success(let me):
            guard isSignedIn else { return nil }
            guard StaffAccess.isStaff(me.roles) else {
                endSession(reason: "PERMISSION_DENIED")
                return nil
            }
            profile = me
            let changed = Set(me.roles) != Set(roles)
            adopt(roles: me.roles)
            if changed, let current = navigator.selection, !can(current) { navigator.reset(for: access) }
            return nil
        }
    }

    /// The dashboard's counts, for the badges beside the sidebar's queues.
    ///
    /// It runs every minute on every shell, so it is also where a role taken
    /// away mid-session is noticed: a 403 here asks the server who this is.
    func refreshAttention() async {
        guard isSignedIn else { return }
        switch await send(AdminAPI.dashboard()) {
        case .success(let snapshot):
            attention = snapshot.attention
            settlementsOpen = snapshot.finance.settlementsOpen
        case .failure(let error):
            if error.httpStatus == 403 { await recheckStaff() }
        }
    }

    /// What waits in a queue, for its badge. Zero shows none.
    func badge(for route: Route) -> Int {
        guard let attention else { return 0 }
        return switch route {
        case .dispatch: attention.unassignedTrips
        case .trips: attention.overdueTrips
        case .liveRequests: attention.unansweredRequests
        case .driverApprovals: attention.pendingDrivers
        case .vehicleApprovals: attention.pendingVehicles
        case .support: attention.openTickets
        case .payouts: settlementsOpen ?? 0
        default: 0
        }
    }

    func clearSignOutReason() { signOutReason = nil }

    /// Sign out here, or -- `allDevices` -- revoke every session this account
    /// has. The second needs the server; its failure comes back to show.
    func signOut(allDevices: Bool = false) async -> APIError? {
        if allDevices, case .failure(let error) = await send(API.logoutAllDevices()) { return error }
        endSession(reason: nil)
        return nil
    }

    private func adopt(roles: [String]) {
        self.roles = roles
        UserDefaults.standard.set(roles, forKey: Self.rolesKey)
    }

    private func applyLocale() {
        UserDefaults.standard.set(locale.tag, forKey: Self.localeKey)
        strings = Strings.load(locale)
        guard isSignedIn else { return }
        let chosen = locale
        Task { _ = await send(API.updateProfile(locale: chosen)) }
    }

    private func endSession(reason: String?) {
        store.clear()
        UserDefaults.standard.removeObject(forKey: Self.rolesKey)
        profile = nil
        roles = []
        attention = nil
        settlementsOpen = nil
        isSignedIn = false
        signOutReason = reason
        navigator.reset(for: StaffAccess(roles: []))
    }
}
