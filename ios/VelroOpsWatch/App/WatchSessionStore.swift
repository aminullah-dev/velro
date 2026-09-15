import Foundation
import VelroCore

/// The watch's own session, in its own keychain entry.
///
/// Its own sign-in, not the phone's session handed over: refresh tokens
/// rotate on every use and a replayed one is treated as theft -- every
/// session the account has is revoked (backend RefreshSession). A token
/// shared by phone and watch would be used by whichever renewed first and
/// then replayed by the other, signing the operator out everywhere.
///
/// The one thing lent out is the access token, to the complications, until
/// it expires; the refresh token stays here.
final class WatchSessionStore: SessionStore, @unchecked Sendable {
    private let keychain: KeychainSessionStore

    init(service: String) {
        keychain = KeychainSessionStore(service: service)
    }

    var accessToken: String? { keychain.accessToken }
    var refreshToken: String? { keychain.refreshToken }
    var userId: String? { keychain.userId }
    var deviceId: String { keychain.deviceId }

    func save(_ session: SessionDTO) {
        keychain.save(session)
        let expires = Date().addingTimeInterval(TimeInterval(session.expiresInSeconds))
        SharedVault.write(WidgetToken(accessToken: session.accessToken, expiresAt: expires), .token)
    }

    func clear() {
        keychain.clear()
        SharedVault.delete(.token)
    }
}
