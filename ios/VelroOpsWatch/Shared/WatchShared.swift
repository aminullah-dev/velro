import Foundation
import Security
import SwiftUI
import VelroCore

// What the watch app and its complications share. Compiled into both
// targets (project.yml), so the two cannot disagree about a shape.

enum WatchShared {
    /// The keychain access group both targets hold, under the team's prefix:
    /// the summary, the language and the borrowed access token live in the
    /// keychain rather than in a plain file. Not an App Group, which would
    /// have to be registered with Apple before anything could be signed.
    /// Read from Info.plist, so the entitlement and the code name one group.
    static let accessGroup: String =
        Bundle.main.object(forInfoDictionaryKey: "VelroSharedGroup") as? String ?? "27RXPRW77S.af.velro.ops.shared"

    /// The complication's kind, for `WidgetCenter`.
    static let widgetKind = "af.velro.ops.watch.attention"
}

// MARK: - What is shared

/// The language the watch is read in, and whether anybody is signed in --
/// what a complication needs before it can say anything at all.
struct WatchPrefs: Codable, Sendable, Equatable {
    var locale: String
    var signedIn: Bool
}

/// The access token, lent to the complications until it expires.
///
/// Only the access token. Refresh tokens rotate and a replayed one revokes
/// every session the account has (backend RefreshSession), so the refresh
/// token never leaves the watch app's own keychain entry and a complication
/// never renews anything: once this has expired it shows what it has.
struct WidgetToken: Codable, Sendable, Equatable {
    var accessToken: String
    var expiresAt: Date
}

/// The "needs attention" block, reduced to what a watch face can show.
struct AttentionSummary: Codable, Sendable, Equatable {
    struct Line: Codable, Sendable, Equatable, Identifiable {
        /// The dashboard's own label, for the app.
        let key: String
        /// A label short enough for a complication's line.
        let shortKey: String
        let count: Int
        /// Asks somebody to act: amber. Papers running out do not, yet.
        let urgent: Bool
        var id: String { key }
    }

    /// Everything that asks somebody to act, each thing once: the sidebar's
    /// badges summed (VelroCore's `Attention.total` plus open settlements).
    /// Departures at risk are already among the trips with no driver, and
    /// papers expiring within 30 days are a warning, so neither is added.
    let total: Int
    /// Only the nonzero figures, most urgent first.
    let lines: [Line]
    /// When these figures were true: the server's time, else their arrival.
    let asOf: Date

    init(total: Int, lines: [Line], asOf: Date) {
        self.total = total
        self.lines = lines
        self.asOf = asOf
    }

    init(snapshot: DashboardSnapshot, fetchedAt: Date) {
        self.init(
            total: Self.total(snapshot),
            lines: Self.lines(snapshot),
            asOf: snapshot.generated ?? fetchedAt
        )
    }

    static func total(_ snapshot: DashboardSnapshot) -> Int {
        snapshot.attention.total + snapshot.finance.settlementsOpen
    }

    /// The web panel's attention cards, in its order of urgency: what strands
    /// a passenger in the next hour first, paperwork last.
    static func lines(_ snapshot: DashboardSnapshot) -> [Line] {
        let a = snapshot.attention
        let all: [Line] = [
            Line(key: "admin.stat.departures_at_risk", shortKey: "admin.stat.departures_at_risk",
                 count: a.departuresAtRisk, urgent: true),
            Line(key: "admin.stat.unassigned", shortKey: "ops.watch.short.unassigned",
                 count: a.unassignedTrips, urgent: true),
            Line(key: "admin.stat.overdue", shortKey: "admin.stat.overdue", count: a.overdueTrips, urgent: true),
            Line(key: "admin.stat.unanswered_requests", shortKey: "ops.watch.short.unanswered_requests",
                 count: a.unansweredRequests, urgent: true),
            Line(key: "admin.stat.stale_gps", shortKey: "ops.watch.short.stale_gps",
                 count: a.staleGpsDrivers, urgent: true),
            Line(key: "admin.section.pending_drivers", shortKey: "ops.watch.short.pending_drivers",
                 count: a.pendingDrivers, urgent: true),
            Line(key: "admin.vehicles.pending", shortKey: "ops.watch.short.pending_vehicles",
                 count: a.pendingVehicles, urgent: true),
            Line(key: "admin.stat.pending_documents", shortKey: "admin.stat.pending_documents",
                 count: a.pendingDocuments, urgent: true),
            Line(key: "admin.stat.open_tickets", shortKey: "ops.watch.short.open_tickets",
                 count: a.openTickets, urgent: true),
            Line(key: "admin.stat.settlements_open", shortKey: "admin.stat.settlements_open",
                 count: snapshot.finance.settlementsOpen, urgent: true),
            Line(key: "admin.stat.expiring_documents", shortKey: "ops.watch.short.expiring_documents",
                 count: a.expiringDocuments, urgent: false),
        ]
        return all.filter { $0.count > 0 }
    }
}

// MARK: - Where it is kept

/// The shared keychain items. Small JSON blobs, readable after the first
/// unlock -- a complication refreshes while the watch is locked on the
/// wrist -- and never included in a backup.
enum SharedVault {
    enum Item: String {
        case prefs
        case summary
        case token = "widget_token"
    }

    private static let service = "af.velro.ops.watch.shared"

    static func read<T: Decodable>(_ type: T.Type, _ item: Item) -> T? {
        var query = base(item)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess,
              let data = result as? Data
        else { return nil }
        return try? JSONDecoder().decode(T.self, from: data)
    }

    static func write(_ value: some Encodable, _ item: Item) {
        guard let data = try? JSONEncoder().encode(value) else { return }
        let status = SecItemUpdate(base(item) as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var add = base(item)
            add[kSecValueData as String] = data
            add[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            SecItemAdd(add as CFDictionary, nil)
        }
    }

    static func delete(_ item: Item) {
        SecItemDelete(base(item) as CFDictionary)
    }

    private static func base(_ item: Item) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: item.rawValue,
            kSecAttrAccessGroup as String: WatchShared.accessGroup,
        ]
    }
}

// MARK: - How it is written

enum WatchFormat {
    /// "۱,۲۰۰" / "1,200".
    static func count(_ value: Int, _ strings: Strings) -> String {
        var grouped = ""
        for (index, character) in String(value.magnitude).reversed().enumerated() {
            if index > 0 && index % 3 == 0 { grouped.append(",") }
            grouped.append(character)
        }
        let number = Numerals.localise(String(grouped.reversed()), strings.locale)
        return value < 0 ? MoneyFormatter.signed(number, negative: true) : number
    }

    /// "۱۲/۲۰": seats sold of seats, held in one left-to-right run, or a
    /// right-to-left line would read it as twenty out of twelve.
    static func fraction(_ part: Int, of whole: Int, _ strings: Strings) -> String {
        "\u{2066}" + count(part, strings) + "/" + count(whole, strings) + "\u{2069}"
    }

    /// "5 min ago", "3 h ago", "2 days ago", in the reader's digits.
    static func age(since date: Date, now: Date = .now, _ strings: Strings) -> String {
        let minutes = max(0, Int(now.timeIntervalSince(date) / 60))
        if minutes < 60 { return strings["common.value.minutes_ago", ["minutes": minutes]] }
        let hours = minutes / 60
        if hours < 48 { return strings["common.value.hours_ago", ["hours": hours]] }
        return strings["common.value.days_ago", ["days": hours / 24]]
    }
}

enum WatchPalette {
    /// The console's one accent: the brand's amber (Palette.amber500).
    static let amber = Color(red: 0xD9 / 255, green: 0x77 / 255, blue: 0x06 / 255)
    /// A number that needs somebody, on the watch's black: the panel's
    /// dark-theme attention colour.
    static let attention = Color(red: 0xFC / 255, green: 0xCF / 255, blue: 0x7A / 255)
    /// Nothing waiting: the brand's lightest green.
    static let clear = Color(red: 0x8F / 255, green: 0xD9 / 255, blue: 0xBC / 255)
}
