import Foundation

/// The last answer the server gave, kept on disk.
///
/// Connections in Ghorband come and go, and a passenger opening the app in a
/// dead spot should see her journeys, labelled as saved, rather than an error
/// about journeys the app cannot currently check. What is kept is the
/// response exactly as it came, so a cached screen and a live one are read
/// by the same decoder.
public final class ResponseCache: Sendable {
    private let directory: URL

    /// `name` separates what belongs to the signed-in person, which is wiped
    /// at sign-out on a shared handset, from what does not (the map of places).
    public init(name: String) {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        directory = base.appending(path: "velro-cache/\(name)", directoryHint: .isDirectory)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    public func store(_ data: Data, key: String) {
        try? data.write(to: file(key), options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }

    public func load(_ key: String) -> Data? { try? Data(contentsOf: file(key)) }

    /// The cached answer, read as the live one would be.
    public func value<T: Decodable>(_ type: T.Type, key: String) -> T? {
        load(key).flatMap { try? APIClient.decoder().decode(Envelope<T>.self, from: $0).data }
    }

    public func clear() {
        try? FileManager.default.removeItem(at: directory)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    }

    private func file(_ key: String) -> URL {
        directory.appending(path: key.replacingOccurrences(of: "/", with: "_") + ".json")
    }
}

/// A live answer, or the saved one with the reason the live one failed.
public struct CachedResult<T: Sendable>: Sendable {
    public let value: T?
    public let error: APIError?

    /// The value is what was saved, not what the server just said.
    public var isStale: Bool { error != nil && value != nil }
}

extension APIClient {
    /// Ask the server; keep its answer; fall back to the last one kept.
    public func send<T>(_ endpoint: Endpoint<T>, caching key: String, in cache: ResponseCache) async -> CachedResult<T> {
        switch await raw(endpoint) {
        case .success(let data):
            guard let value = try? Self.decoder().decode(Envelope<T>.self, from: data).data else {
                return CachedResult(value: cache.value(T.self, key: key), error: .unknown(reason: "response_unreadable"))
            }
            cache.store(data, key: key)
            return CachedResult(value: value, error: nil)
        case .failure(let error):
            return CachedResult(value: cache.value(T.self, key: key), error: error)
        }
    }
}
