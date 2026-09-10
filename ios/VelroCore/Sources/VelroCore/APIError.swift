/// The server's response envelope. Every answer has this shape, so there is
/// one format to read.
struct Envelope<T: Decodable>: Decodable {
    let data: T?
}

struct ErrorEnvelope: Decodable {
    struct Body: Decodable {
        let code: String
        let context: [String: JSONValue]?
        let requestId: String?
    }
    let error: Body
}

/// A failure a screen can act on.
///
/// `code` drives behaviour, `context` fills the translated sentence, and
/// `requestId` is what support asks for. The server's wording is never carried:
/// the phone says it in the language being read.
public struct APIError: Error, Sendable, Equatable {
    public let code: String
    public let httpStatus: Int
    public let context: [String: JSONValue]
    public let requestId: String?

    public init(
        code: String,
        httpStatus: Int,
        context: [String: JSONValue] = [:],
        requestId: String? = nil
    ) {
        self.code = code
        self.httpStatus = httpStatus
        self.context = context
        self.requestId = requestId
    }

    public static let offlineCode = "NETWORK_OFFLINE"
    public static let unknownCode = "INTERNAL_ERROR"
    public static let cancelledCode = "CANCELLED"

    /// No connection, a DNS failure, a timeout. Said in those words, never as
    /// "something went wrong".
    public static let offline = APIError(code: offlineCode, httpStatus: 0)

    /// The screen went away mid-request. Nothing to show anybody.
    public static let cancelled = APIError(code: cancelledCode, httpStatus: 0)

    public static func unknown(status: Int = 0, reason: String? = nil) -> APIError {
        APIError(
            code: unknownCode,
            httpStatus: status,
            context: reason.map { ["reason": .string($0)] } ?? [:]
        )
    }

    public var isAuthFailure: Bool {
        ["TOKEN_INVALID", "TOKEN_EXPIRED", "REFRESH_TOKEN_REVOKED"].contains(code)
    }

    /// Worth retrying by itself; a conflict or a validation failure is not.
    public var isTransient: Bool {
        httpStatus >= 500 || code == "RATE_LIMITED" || code == Self.offlineCode
    }
}
