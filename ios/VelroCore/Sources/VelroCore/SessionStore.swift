import Foundation
import Security

/// A signed-in session, as the server issues it.
public struct SessionDTO: Codable, Sendable, Equatable {
    public let userId: String
    public let accessToken: String
    public let refreshToken: String
    public let roles: [String]
    public let isNewUser: Bool
    public let expiresInSeconds: Int

    public init(
        userId: String, accessToken: String, refreshToken: String,
        roles: [String], isNewUser: Bool, expiresInSeconds: Int
    ) {
        self.userId = userId
        self.accessToken = accessToken
        self.refreshToken = refreshToken
        self.roles = roles
        self.isNewUser = isNewUser
        self.expiresInSeconds = expiresInSeconds
    }
}

/// Where the session lives. A protocol so the refresh logic can be tested with
/// several requests racing, which must not need a device to find out.
public protocol SessionStore: Sendable {
    var accessToken: String? { get }
    var refreshToken: String? { get }
    var userId: String? { get }
    /// Generated once and kept across sign-outs, so "sign out of all devices"
    /// can tell this phone from the others.
    var deviceId: String { get }
    func save(_ session: SessionDTO)
    /// Ends the session but keeps the device id.
    func clear()
}

/// The session in the Keychain, readable only on this device after the first
/// unlock -- tokens must not travel to a new iPhone inside a backup.
public final class KeychainSessionStore: SessionStore, @unchecked Sendable {
    private let service: String
    private let lock = NSLock()
    private var cache: [String: String] = [:]

    private enum Key {
        static let access = "access_token"
        static let refresh = "refresh_token"
        static let user = "user_id"
        static let device = "device_id"
    }

    public init(service: String) {
        self.service = service
        // Keychain items outlive the app on iOS. A phone passed to someone else
        // after a reinstall would otherwise open signed in as the last person,
        // and a shared handset is the normal case here -- so a first launch
        // starts from nothing.
        let marker = "\(service).installed"
        if !UserDefaults.standard.bool(forKey: marker) {
            for key in [Key.access, Key.refresh, Key.user, Key.device] { delete(key) }
            UserDefaults.standard.set(true, forKey: marker)
        }
    }

    public var accessToken: String? { value(Key.access) }
    public var refreshToken: String? { value(Key.refresh) }
    public var userId: String? { value(Key.user) }

    public var deviceId: String {
        if let existing = value(Key.device) { return existing }
        let generated = UUID().uuidString.lowercased()
        write(Key.device, generated)
        return generated
    }

    public func save(_ session: SessionDTO) {
        write(Key.access, session.accessToken)
        write(Key.refresh, session.refreshToken)
        write(Key.user, session.userId)
    }

    public func clear() {
        for key in [Key.access, Key.refresh, Key.user] { delete(key) }
    }

    // MARK: Keychain

    private func value(_ key: String) -> String? {
        lock.lock()
        defer { lock.unlock() }
        if let cached = cache[key] { return cached }
        var query = base(key)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        guard
            SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
            let data = result as? Data,
            let string = String(data: data, encoding: .utf8)
        else { return nil }
        cache[key] = string
        return string
    }

    private func write(_ key: String, _ value: String) {
        lock.lock()
        defer { lock.unlock() }
        let data = Data(value.utf8)
        let update: [String: Any] = [kSecValueData as String: data]
        let status = SecItemUpdate(base(key) as CFDictionary, update as CFDictionary)
        if status == errSecItemNotFound {
            var add = base(key)
            add[kSecValueData as String] = data
            add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            SecItemAdd(add as CFDictionary, nil)
        }
        cache[key] = value
    }

    private func delete(_ key: String) {
        lock.lock()
        defer { lock.unlock() }
        SecItemDelete(base(key) as CFDictionary)
        cache[key] = nil
    }

    private func base(_ key: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
        ]
    }
}

/// A session held in memory, for tests and previews.
public final class MemorySessionStore: SessionStore, @unchecked Sendable {
    private let lock = NSLock()
    private var session: SessionDTO?
    private let device = UUID().uuidString.lowercased()

    public init(_ session: SessionDTO? = nil) { self.session = session }

    public var accessToken: String? { lock.withLock { session?.accessToken } }
    public var refreshToken: String? { lock.withLock { session?.refreshToken } }
    public var userId: String? { lock.withLock { session?.userId } }
    public var deviceId: String { device }
    public func save(_ session: SessionDTO) { lock.withLock { self.session = session } }
    public func clear() { lock.withLock { session = nil } }
}
