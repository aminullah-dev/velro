import Foundation
import Testing
@testable import VelroCore

/// A server in a box: every request the client makes lands in `handler`.
final class StubServer: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var handler: (@Sendable (URLRequest) throws -> (Int, String))?
    private static let lock = NSLock()
    nonisolated(unsafe) private static var seen: [String] = []

    static func reset(_ handler: @escaping @Sendable (URLRequest) throws -> (Int, String)) {
        lock.withLock { seen = [] }
        self.handler = handler
    }

    static func count(_ path: String) -> Int {
        lock.withLock { seen.filter { $0.hasSuffix(path) }.count }
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        let path = request.url?.path ?? ""
        Self.lock.withLock { Self.seen.append(path) }
        do {
            guard let handler = Self.handler else { throw URLError(.badServerResponse) }
            let (status, body) = try handler(request)
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(body.utf8))
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }
}

private let expired = #"{"success":false,"error":{"code":"TOKEN_EXPIRED","message_key":"error.token_expired","context":{},"request_id":"r1"}}"#
private let renewed = #"{"success":true,"data":{"user_id":"u1","access_token":"new","refresh_token":"r2","roles":["passenger"],"is_new_user":false,"expires_in_seconds":900}}"#
private let profile = #"{"success":true,"data":{"id":"u1","phone":"+93700000800","full_name":null,"locale":"fa-AF","status":"ACTIVE","roles":["passenger"],"completed_trips":0,"rating_count":0}}"#

private func session() -> SessionDTO {
    SessionDTO(userId: "u1", accessToken: "old", refreshToken: "r1", roles: ["passenger"], isNewUser: false, expiresInSeconds: 900)
}

private final class Flag: @unchecked Sendable {
    private let lock = NSLock()
    private var raised = false
    func raise() { lock.withLock { raised = true } }
    var isRaised: Bool { lock.withLock { raised } }
}

private func client(_ store: SessionStore, ended: Flag = Flag()) -> APIClient {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [StubServer.self]
    return APIClient(
        baseURL: URL(string: "http://test.invalid/api/v1/")!,
        store: store,
        transport: URLSession(configuration: configuration),
        onSessionEnded: { ended.raise() }
    )
}

@Suite(.serialized) struct APIClientTests {
    @Test func anEnvelopeIsUnwrapped() async throws {
        StubServer.reset { _ in (200, profile) }
        let result = await client(MemorySessionStore(session())).send(API.profile())
        #expect(try result.get().phone == "+93700000800")
    }

    @Test func aServerErrorKeepsItsCodeAndContext() async {
        StubServer.reset { _ in
            (400, #"{"success":false,"error":{"code":"OTP_INVALID","context":{"attempts_remaining":2},"request_id":"abc"}}"#)
        }
        let result = await client(MemorySessionStore()).send(
            API.verifyOtp(phone: "0700000800", code: "0000", deviceId: "d", locale: .dari)
        )
        guard case .failure(let error) = result else { Issue.record("expected a failure"); return }
        #expect(error.code == "OTP_INVALID")
        #expect(error.context["attempts_remaining"] == .int(2))
        #expect(error.requestId == "abc")
    }

    @Test func noConnectionIsSaidAsNoConnection() async {
        StubServer.reset { _ in throw URLError(.notConnectedToInternet) }
        let result = await client(MemorySessionStore(session())).send(API.profile())
        #expect(result == .failure(.offline))
    }

    /// Five requests expire in the same second; one refresh renews them all.
    @Test func manyExpiriesSpendOneRefresh() async throws {
        StubServer.reset { request in
            if request.url!.path.hasSuffix("auth/refresh") {
                Thread.sleep(forTimeInterval: 0.2)
                return (200, renewed)
            }
            return request.value(forHTTPHeaderField: "Authorization") == "Bearer new" ? (200, profile) : (401, expired)
        }
        let store = MemorySessionStore(session())
        let api = client(store)
        let results = await withTaskGroup(of: Result<ProfileDTO, APIError>.self) { group in
            for _ in 0..<5 { group.addTask { await api.send(API.profile()) } }
            return await group.reduce(into: []) { $0.append($1) }
        }
        #expect(results.allSatisfy { (try? $0.get()) != nil })
        #expect(StubServer.count("auth/refresh") == 1)
        #expect(store.accessToken == "new")
        #expect(store.refreshToken == "r2")
    }

    @Test func aRefusedRefreshEndsTheSession() async {
        StubServer.reset { request in
            request.url!.path.hasSuffix("auth/refresh")
                ? (401, #"{"success":false,"error":{"code":"REFRESH_TOKEN_REVOKED","context":{}}}"#)
                : (401, expired)
        }
        let store = MemorySessionStore(session())
        let ended = Flag()
        let result = await client(store, ended: ended).send(API.profile())
        #expect(result == .failure(APIError(code: "TOKEN_EXPIRED", httpStatus: 401, requestId: "r1")))
        #expect(store.accessToken == nil)
        #expect(ended.isRaised)
    }

    /// A refresh that cannot reach the server is not the end of a session.
    @Test func anUnreachableRefreshKeepsTheSession() async {
        StubServer.reset { request in
            if request.url!.path.hasSuffix("auth/refresh") { throw URLError(.networkConnectionLost) }
            return (401, expired)
        }
        let store = MemorySessionStore(session())
        let ended = Flag()
        let result = await client(store, ended: ended).send(API.profile())
        #expect(result == .failure(.offline))
        #expect(store.refreshToken == "r1")
        #expect(!ended.isRaised)
    }

    @Test func idempotencyKeysKeepTheAndroidShapes() {
        #expect(IdempotencyKeys.acceptOffer(offerId: "o1", attemptId: "a1") == "accept_offer:o1:a1")
        #expect(IdempotencyKeys.ask(originStationId: "s", destinationId: "d", seats: 2, attemptId: "a") == "ask:s:d:2:a")
    }
}
