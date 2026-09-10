import Foundation

/// The driver's side of a negotiation, played by the test through the API on
/// this Mac. A seeded, approved, online driver from the development database;
/// the development server echoes his sign-in code, so no message is sent.
struct LocalDriver {
    private let api = URL(string: "http://localhost:8000/api/v1/")!
    let phone = "+93700000020"

    struct Failure: Error, CustomStringConvertible { let description: String }

    func signIn() async throws -> String {
        let sent = try await call("auth/otp/request", body: ["phone": phone, "locale": "en", "channel": "sms"])
        guard let code = (sent["data"] as? [String: Any])?["debug_code"] as? String else {
            throw Failure(description: "no echoed code -- is `make api` running with echo on? \(sent)")
        }
        let session = try await call("auth/otp/verify", body: ["phone": phone, "code": code, "device_id": "ui-test-driver", "locale": "en"])
        guard let token = (session["data"] as? [String: Any])?["access_token"] as? String else {
            throw Failure(description: "driver sign-in refused: \(session)")
        }
        return token
    }

    /// Ends any trip a failed earlier run left him on: a driver already on a
    /// trip may not bid, and one broken run must not break every run after it.
    func releaseCurrentTrip(token: String) async throws {
        let current = try await call("driver/trips/current", token: token)
        guard let trip = (current["data"] as? [String: Any])?["trip"] as? [String: Any],
              let id = trip["id"] as? String else { return }
        _ = try await call("driver/trips/\(id)/advance", body: ["target": "CANCELLED", "reason_code": "DRIVER_CANCELLED"], token: token)
    }

    /// Names a price on the newest open request he has not answered yet.
    func offerOnNewestRequest(token: String, amountMinor: Int) async throws {
        let board = try await call("driver/ride-requests", token: token)
        let requests = (board["data"] as? [[String: Any]]) ?? []
        let open = requests
            .filter { ($0["already_offered"] as? Bool) != true }
            .sorted { ($0["created_at"] as? String ?? "") > ($1["created_at"] as? String ?? "") }
        guard let id = open.first?["id"] as? String else {
            throw Failure(description: "no open request on the driver's board: \(board)")
        }
        let offered = try await call("driver/ride-requests/\(id)/offer", body: ["amount_minor": amountMinor], token: token)
        guard offered["success"] as? Bool == true else { throw Failure(description: "offer refused: \(offered)") }
    }

    private func call(_ path: String, body: [String: Any]? = nil, token: String? = nil) async throws -> [String: Any] {
        var request = URLRequest(url: api.appending(path: path))
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let body {
            request.httpMethod = "POST"
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, _) = try await URLSession.shared.data(for: request)
        return (try JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }
}
