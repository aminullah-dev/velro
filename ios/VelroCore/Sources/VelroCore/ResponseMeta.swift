import Foundation

/// The envelope's `meta`: a list's page and total, or a board's counts.
///
/// Every field is optional because each endpoint fills a different few:
/// `admin/trips` sends total, limit and offset; `dispatch/unassigned` sends
/// count, at_risk and drivers_available.
public struct ResponseMeta: Decodable, Sendable, Hashable {
    public let total: Int?
    public let limit: Int?
    public let offset: Int?
    public let count: Int?
    public let atRisk: Int?
    public let driversAvailable: Int?

    public init(
        total: Int? = nil, limit: Int? = nil, offset: Int? = nil,
        count: Int? = nil, atRisk: Int? = nil, driversAvailable: Int? = nil
    ) {
        self.total = total
        self.limit = limit
        self.offset = offset
        self.count = count
        self.atRisk = atRisk
        self.driversAvailable = driversAvailable
    }
}

/// The success envelope with its meta, for `APIClient.sendWithMeta`.
struct MetaEnvelope<T: Decodable>: Decodable {
    let data: T?
    let meta: ResponseMeta?
}

/// An answer with its meta kept: see `APIClient.sendWithMeta`.
public struct Paged<Value: Sendable>: Sendable {
    public let value: Value
    public let meta: ResponseMeta

    public init(value: Value, meta: ResponseMeta) {
        self.value = value
        self.meta = meta
    }
}

extension Paged where Value: Collection {
    public var items: Value { value }

    /// More rows past this page, by the server's total.
    public var hasMore: Bool {
        guard let total = meta.total else { return false }
        return (meta.offset ?? 0) + value.count < total
    }

    /// Where the next page starts.
    public var nextOffset: Int { (meta.offset ?? 0) + value.count }
}

extension Paged: Equatable where Value: Equatable {}

/// A file the server serves as bytes rather than JSON -- a driver's licence,
/// a tazkira, a vehicle's papers. Fetched with `APIClient.download`, which
/// carries the bearer token and renews it like any other call: these files
/// are never on a public path.
///
/// Held in memory only. They are identity documents; the server marks them
/// no-store, and nothing here writes them to disk.
public struct DownloadedFile: Decodable, Sendable, Hashable {
    public let data: Data
    /// The server's Content-Type: "image/jpeg", "image/png", "application/pdf".
    public let contentType: String?

    public init(data: Data, contentType: String?) {
        self.data = data
        self.contentType = contentType
    }

    public var isImage: Bool { contentType?.lowercased().hasPrefix("image/") == true }
    public var isPDF: Bool { contentType?.lowercased().hasPrefix("application/pdf") == true }
}
