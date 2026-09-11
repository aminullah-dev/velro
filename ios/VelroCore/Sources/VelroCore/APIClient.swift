import Foundation

/// One call to the API, typed by what it answers with.
public struct Endpoint<Response: Decodable & Sendable>: Sendable {
    public enum Method: String, Sendable { case get = "GET", post = "POST", patch = "PATCH", delete = "DELETE" }

    public var method: Method
    public var path: String
    public var query: [URLQueryItem] = []
    public var body: Data?
    /// Every mutation that must not happen twice carries one; see
    /// `IdempotencyKeys`.
    public var idempotencyKey: String?
    public var authenticated = true

    public static func get(_ path: String, query: [URLQueryItem] = []) -> Self {
        Endpoint(method: .get, path: path, query: query)
    }

    public static func post(
        _ path: String,
        body: some Encodable = [String: String](),
        idempotencyKey: String? = nil,
        authenticated: Bool = true
    ) -> Self {
        Endpoint(
            method: .post, path: path, body: APIClient.encode(body),
            idempotencyKey: idempotencyKey, authenticated: authenticated
        )
    }

    public static func patch(_ path: String, body: some Encodable) -> Self {
        Endpoint(method: .patch, path: path, body: APIClient.encode(body))
    }

    public static func delete(_ path: String) -> Self {
        Endpoint(method: .delete, path: path)
    }
}

/// The HTTP client.
///
/// Three kinds of failure are kept apart because a screen treats them
/// differently: no connection at all, a structured server error to translate,
/// and an answer nobody can read. An expired access token is renewed once --
/// exactly once, however many requests expire together -- and the request
/// replayed.
public final class APIClient: Sendable {
    public let baseURL: URL
    let store: any SessionStore
    private let transport: URLSession
    private let coordinator = RefreshCoordinator()
    private let sessionEnded: @Sendable () -> Void

    public init(
        baseURL: URL,
        store: any SessionStore,
        transport: URLSession = .shared,
        onSessionEnded: @escaping @Sendable () -> Void = {}
    ) {
        self.baseURL = baseURL
        self.store = store
        self.transport = transport
        self.sessionEnded = onSessionEnded
    }

    /// The call, for endpoints whose answer is always an object. A 2xx with
    /// no payload is a fault, and fails loudly rather than handing a screen a
    /// nil to crash on.
    public func send<T>(_ endpoint: Endpoint<T>) async -> Result<T, APIError> {
        switch await sendNullable(endpoint) {
        case .success(.some(let value)): .success(value)
        case .success(.none): .failure(.unknown(status: 200, reason: "empty_payload"))
        case .failure(let error): .failure(error)
        }
    }

    /// The call, for the endpoints where `data: null` is an answer -- "there
    /// is no current trip" is not a failed read.
    public func sendNullable<T>(_ endpoint: Endpoint<T>) async -> Result<T?, APIError> {
        switch await exchange(endpoint, isRetry: false) {
        case .failure(let error):
            return .failure(error)
        case .success(let data):
            do {
                return .success(try Self.decoder().decode(Envelope<T>.self, from: data).data)
            } catch {
                // The server answered and it could not be read: a contract
                // mismatch, not a network problem, and reported as such.
                return .failure(.unknown(reason: "response_unreadable"))
            }
        }
    }

    func raw<T>(_ endpoint: Endpoint<T>) async -> Result<Data, APIError> {
        await exchange(endpoint, isRetry: false)
    }

    private func exchange<T>(_ endpoint: Endpoint<T>, isRetry: Bool) async -> Result<Data, APIError> {
        let token = endpoint.authenticated ? store.accessToken : nil
        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await transport.data(for: request(for: endpoint, token: token))
        } catch is CancellationError {
            return .failure(.cancelled)
        } catch let error as URLError where error.code == .cancelled {
            return .failure(.cancelled)
        } catch {
            return .failure(.offline)
        }
        guard let http = response as? HTTPURLResponse else { return .failure(.unknown()) }
        if (200..<300).contains(http.statusCode) { return .success(data) }

        if http.statusCode == 401, token != nil, !isRetry {
            switch await coordinator.renew(used: token, client: self) {
            case .renewed:
                return await exchange(endpoint, isRetry: true)
            case .unreachable:
                return .failure(.offline)
            case .ended:
                sessionEnded()
            }
        }
        return .failure(Self.error(from: data, status: http.statusCode))
    }

    /// Renew the session.
    ///
    /// Only a refusal from the server ends it. The Android client clears the
    /// session on any failure here, network included, which signs somebody
    /// out for driving into a valley with no signal; a refresh that could not
    /// reach the server leaves the session alone and the request fails as
    /// offline instead.
    func refresh() async -> RenewOutcome {
        guard let refreshToken = store.refreshToken else {
            store.clear()
            return .ended
        }
        struct Body: Encodable { let refreshToken: String; let deviceId: String }
        let endpoint = Endpoint<SessionDTO>.post(
            "auth/refresh",
            body: Body(refreshToken: refreshToken, deviceId: store.deviceId),
            authenticated: false
        )
        do {
            let (data, response) = try await transport.data(for: request(for: endpoint, token: nil))
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            if (200..<300).contains(status),
               let session = try? Self.decoder().decode(Envelope<SessionDTO>.self, from: data).data {
                store.save(session)
                return .renewed
            }
            if status == 429 || status >= 500 || status == 0 { return .unreachable }
            store.clear()
            return .ended
        } catch {
            return .unreachable
        }
    }

    private func request<T>(for endpoint: Endpoint<T>, token: String?) -> URLRequest {
        var url = baseURL.appending(path: endpoint.path)
        if !endpoint.query.isEmpty { url.append(queryItems: endpoint.query) }
        var request = URLRequest(url: url, timeoutInterval: 30)
        request.httpMethod = endpoint.method.rawValue
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        // Made here so a request can be traced end to end even when the
        // answer never arrives.
        request.setValue(UUID().uuidString.lowercased(), forHTTPHeaderField: "X-Request-ID")
        if let body = endpoint.body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let key = endpoint.idempotencyKey { request.setValue(key, forHTTPHeaderField: "Idempotency-Key") }
        return request
    }

    static func error(from data: Data, status: Int) -> APIError {
        guard let body = try? decoder().decode(ErrorEnvelope.self, from: data) else {
            return .unknown(status: status)
        }
        return APIError(
            code: body.error.code,
            httpStatus: status,
            context: body.error.context ?? [:],
            requestId: body.error.requestId
        )
    }

    /// The payload of an envelope already fetched as bytes.
    public static func decodeEnvelope<T: Decodable>(_ data: Data, as type: T.Type) -> T? {
        try? decoder().decode(Envelope<T>.self, from: data).data
    }

    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    static func encode(_ body: some Encodable) -> Data? {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return try? encoder.encode(body)
    }
}

enum RenewOutcome: Sendable {
    case renewed, ended, unreachable
}

/// Makes sure one refresh happens however many requests expire at once.
///
/// Refresh tokens rotate, and the server treats a replayed one as theft and
/// revokes every session the person has. Everything on a screen expires in the
/// same second, so without this the second request's refresh would sign them
/// out of the phone they are using.
actor RefreshCoordinator {
    private var inFlight: Task<RenewOutcome, Never>?

    func renew(used: String?, client: APIClient) async -> RenewOutcome {
        // Already renewed by whoever got here first: just use it.
        if let current = client.store.accessToken, current != used { return .renewed }
        if let inFlight { return await inFlight.value }
        let task = Task { await client.refresh() }
        inFlight = task
        let outcome = await task.value
        inFlight = nil
        return outcome
    }
}
