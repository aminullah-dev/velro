import Foundation

/// The passenger's side of a trip, played by the test through the API on this
/// Mac while the driver's side is the real app. A fresh number from the
/// reserved +93 700 000 xxx range per run; the development server echoes the
/// sign-in code, so no message is sent.
struct LocalPassenger {
    private let api = URL(string: "http://localhost:8000/api/v1/")!
    let phone = String(format: "+93700000%03d", Int.random(in: 810...989))

    struct Failure: Error, CustomStringConvertible { let description: String }

    func signIn() async throws -> String {
        try await Self.signIn(phone: phone, device: "ui-test-passenger")
    }

    static func signIn(phone: String, device: String) async throws -> String {
        let me = LocalPassenger()
        let sent = try await me.call("auth/otp/request", body: ["phone": phone, "locale": "en", "channel": "sms"])
        guard let code = (sent["data"] as? [String: Any])?["debug_code"] as? String else {
            throw Failure(description: "no echoed code -- is `make api` running with echo on? \(sent)")
        }
        let session = try await me.call("auth/otp/verify", body: ["phone": phone, "code": code, "device_id": device, "locale": "en"])
        guard let token = (session["data"] as? [String: Any])?["access_token"] as? String else {
            throw Failure(description: "sign-in refused: \(session)")
        }
        return token
    }

    /// Asks for a ride from ایستگاه خیشکی (Siahgird) to Charikar -- the one
    /// pair the development database has a drawn road for -- tomorrow at seven,
    /// standing at the station so the service-area check lets it through.
    func ask(token: String, fareAfghani: Int) async throws -> String {
        let geo = try await call("geo/snapshot", token: token)
        let stations = ((geo["data"] as? [String: Any])?["stations"] as? [[String: Any]]) ?? []
        guard let station = stations.first(where: { ($0["code"] as? String) == "GRB-SYG-001-S1" }),
              let stationId = station["id"] as? String else { throw Failure(description: "no Siahgird station in the snapshot") }
        let groups = (try await call("geo/stations/\(stationId)/destinations", token: token)["data"] as? [[String: Any]]) ?? []
        // A destination may open into several (Kabul into Khair Khana, Jada);
        // Charikar is one on its own.
        let destinations = groups + groups.flatMap { ($0["children"] as? [[String: Any]]) ?? [] }
        guard let charikar = destinations.first(where: { ($0["code"] as? String) == "EXT-CHK" }) ?? destinations.first,
              let destinationId = charikar["id"] as? String else { throw Failure(description: "no destination from Siahgird") }

        var kabul = Calendar(identifier: .gregorian)
        kabul.timeZone = TimeZone(identifier: "Asia/Kabul")!
        let tomorrow = kabul.date(byAdding: .day, value: 1, to: .now)!
        let seven = kabul.date(bySettingHour: 7, minute: 0, second: 0, of: tomorrow)!
        let formatter = ISO8601DateFormatter()

        let body: [String: Any] = [
            "origin_station_id": stationId,
            "destination_id": destinationId,
            "passenger_count": 1,
            "offered_fare_minor": fareAfghani * 100,
            "requested_for": formatter.string(from: seven),
            "latitude": String(describing: station["latitude"] ?? ""),
            "longitude": String(describing: station["longitude"] ?? ""),
            "note": "UI test",
        ]
        let made = try await call("ride-requests", body: body, token: token, idempotencyKey: UUID().uuidString)
        guard let id = (made["data"] as? [String: Any])?["id"] as? String else { throw Failure(description: "ask refused: \(made)") }
        return id
    }

    /// Accepts the first open offer on the request, and returns the boarding
    /// code the passenger would show the driver.
    func acceptFirstOffer(token: String, requestId: String, timeout: TimeInterval = 30) async throws -> String {
        let deadline = Date.now.addingTimeInterval(timeout)
        while Date.now < deadline {
            let mine = (try await call("ride-requests", token: token)["data"] as? [[String: Any]]) ?? []
            let request = mine.first { ($0["id"] as? String) == requestId }
            let offers = (request?["offers"] as? [[String: Any]]) ?? []
            if let offer = offers.first(where: { ($0["status"] as? String) == "OFFERED" }), let id = offer["id"] as? String {
                let accepted = try await call("fare-offers/\(id)/accept", body: [:], token: token,
                                              idempotencyKey: "accept_offer:\(id):\(UUID().uuidString.lowercased())")
                guard let code = (accepted["data"] as? [String: Any])?["verification_code"] as? String else {
                    throw Failure(description: "accept refused: \(accepted)")
                }
                return code
            }
            try await Task.sleep(for: .seconds(2))
        }
        throw Failure(description: "no offer arrived on \(requestId)")
    }

    /// Ends whatever trip a failed earlier run left the driver on: a driver
    /// already on a trip may not bid, and one broken run must not break every
    /// run after it.
    static func releaseDriver(phone: String) async throws {
        let me = LocalPassenger()
        let token = try await signIn(phone: phone, device: "ui-test-driver")
        let current = try await me.call("driver/trips/current", token: token)
        guard let trip = (current["data"] as? [String: Any])?["trip"] as? [String: Any],
              let id = trip["id"] as? String else { return }
        _ = try await me.call("driver/trips/\(id)/advance", body: ["target": "CANCELLED", "reason_code": "DRIVER_CANCELLED"], token: token)
    }

    private func call(_ path: String, body: [String: Any]? = nil, token: String? = nil, idempotencyKey: String? = nil) async throws -> [String: Any] {
        var request = URLRequest(url: api.appending(path: path))
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let idempotencyKey { request.setValue(idempotencyKey, forHTTPHeaderField: "Idempotency-Key") }
        if let body {
            request.httpMethod = "POST"
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
        }
        let (data, _) = try await URLSession.shared.data(for: request)
        return (try JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }
}
