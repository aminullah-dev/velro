import SwiftUI
import VelroCore
import WidgetKit

/// VELRO Ops on the watch face: how many things need somebody right now.
@main
struct VelroOpsWatchWidgets: WidgetBundle {
    var body: some Widget {
        AttentionWidget()
    }
}

struct AttentionWidget: Widget {
    var body: some WidgetConfiguration {
        let strings = Strings.load(AttentionProvider.prefs().map { AppLocale(tag: $0.locale) } ?? .dari)
        return StaticConfiguration(kind: WatchShared.widgetKind, provider: AttentionProvider()) { entry in
            AttentionWidgetView(entry: entry)
        }
        .configurationDisplayName(strings["admin.ops.attention"])
        .description(strings["ops.watch.widget_description"])
        .supportedFamilies([.accessoryCircular, .accessoryRectangular, .accessoryInline, .accessoryCorner])
    }
}

// MARK: - Timeline

struct AttentionEntry: TimelineEntry, Sendable {
    let date: Date
    let strings: Strings
    let signedIn: Bool
    let summary: AttentionSummary?

    /// Figures older than this say how old they are.
    var isStale: Bool {
        guard let summary else { return false }
        return date.timeIntervalSince(summary.asOf) > 20 * 60
    }
}

/// What the watch app last wrote, fetched again here only while the access
/// token it lent is still valid -- and never renewed here: refresh tokens
/// rotate, and one presented from the app and from here would end every
/// session the account has.
struct AttentionProvider: TimelineProvider {
    static func prefs() -> WatchPrefs? { SharedVault.read(WatchPrefs.self, .prefs) }

    func placeholder(in context: Context) -> AttentionEntry {
        let strings = Strings.load(Self.prefs().map { AppLocale(tag: $0.locale) } ?? .dari)
        let sample = AttentionSummary(
            total: 3,
            lines: [
                .init(key: "admin.stat.departures_at_risk", shortKey: "admin.stat.departures_at_risk", count: 1, urgent: true),
                .init(key: "admin.stat.unassigned", shortKey: "ops.watch.short.unassigned", count: 2, urgent: true),
                .init(key: "admin.stat.open_tickets", shortKey: "ops.watch.short.open_tickets", count: 1, urgent: true),
            ],
            asOf: .now
        )
        return AttentionEntry(date: .now, strings: strings, signedIn: true, summary: sample)
    }

    func getSnapshot(in context: Context, completion: @escaping @Sendable (AttentionEntry) -> Void) {
        completion(context.isPreview && Self.prefs()?.signedIn != true ? placeholder(in: context) : Self.entry(at: .now))
    }

    func getTimeline(in context: Context, completion: @escaping @Sendable (Timeline<AttentionEntry>) -> Void) {
        Task {
            await Self.fetchIfTokenValid()
            // One entry now and two later, so the age a stale summary shows
            // keeps up; asked again in fifteen minutes.
            let now = Date()
            let entries = [0, 5, 10].map { Self.entry(at: now.addingTimeInterval(TimeInterval($0 * 60))) }
            completion(Timeline(entries: entries, policy: .after(now.addingTimeInterval(15 * 60))))
        }
    }

    static func entry(at date: Date) -> AttentionEntry {
        let prefs = prefs()
        let strings = Strings.load(prefs.map { AppLocale(tag: $0.locale) } ?? .dari)
        let signedIn = prefs?.signedIn ?? false
        let summary = signedIn ? SharedVault.read(AttentionSummary.self, .summary) : nil
        return AttentionEntry(date: date, strings: strings, signedIn: signedIn, summary: summary)
    }

    /// admin/dashboard with the access token the app lent, while it is valid.
    /// Anything else -- no token, expired, refused, offline -- leaves the
    /// summary the app wrote.
    static func fetchIfTokenValid() async {
        guard
            prefs()?.signedIn == true,
            let token = SharedVault.read(WidgetToken.self, .token),
            token.expiresAt > Date().addingTimeInterval(30),
            let raw = Bundle.main.object(forInfoDictionaryKey: "VelroAPIBaseURL") as? String,
            let base = URL(string: raw)
        else { return }
        var request = URLRequest(url: base.appending(path: AdminAPI.dashboard().path), timeoutInterval: 15)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("Bearer \(token.accessToken)", forHTTPHeaderField: "Authorization")
        request.setValue(UUID().uuidString.lowercased(), forHTTPHeaderField: "X-Request-ID")
        guard
            let (data, response) = try? await URLSession.shared.data(for: request),
            (response as? HTTPURLResponse)?.statusCode == 200,
            let snapshot = APIClient.decodeEnvelope(data, as: DashboardSnapshot.self),
            // Signed out while this was in flight: keep nothing.
            prefs()?.signedIn == true
        else { return }
        SharedVault.write(AttentionSummary(snapshot: snapshot, fetchedAt: .now), .summary)
    }
}

// MARK: - Views

struct AttentionWidgetView: View {
    @Environment(\.widgetFamily) private var family
    let entry: AttentionEntry

    var body: some View {
        Group {
            switch family {
            case .accessoryCircular: circular
            case .accessoryRectangular: rectangular
            case .accessoryInline: inline
            case .accessoryCorner: corner
            default: circular
            }
        }
        .environment(\.layoutDirection, entry.strings.locale.isRTL ? .rightToLeft : .leftToRight)
        .containerBackground(for: .widget) { Color.clear }
    }

    private var strings: Strings { entry.strings }
    private var total: Int { entry.summary?.total ?? 0 }

    private func count(_ value: Int) -> String { WatchFormat.count(value, strings) }

    private var age: String? {
        guard entry.isStale, let summary = entry.summary else { return nil }
        return WatchFormat.age(since: summary.asOf, now: entry.date, strings)
    }

    // The total in the middle, amber; a tick when nothing waits.
    private var circular: some View {
        ZStack {
            AccessoryWidgetBackground()
            if !entry.signedIn || entry.summary == nil {
                Image(systemName: "person.crop.circle.badge.questionmark")
                    .font(.title3)
            } else if total > 0 {
                VStack(spacing: 0) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 10))
                    Text(count(total))
                        .font(.system(.title2, design: .rounded).weight(.bold))
                        .minimumScaleFactor(0.5)
                        .lineLimit(1)
                }
                .foregroundStyle(WatchPalette.attention)
                .widgetAccentable()
            } else {
                Image(systemName: "checkmark")
                    .font(.title2.weight(.bold))
                    .foregroundStyle(WatchPalette.clear)
                    .widgetAccentable()
            }
        }
        .accessibilityLabel(inlineText)
    }

    // Up to three nonzero lines, the most urgent first.
    private var rectangular: some View {
        VStack(alignment: .leading, spacing: 1) {
            if !entry.signedIn || entry.summary == nil {
                Text(strings["ops.title"])
                    .font(.headline)
                    .widgetAccentable()
                Text(strings[entry.signedIn ? "common.state.loading" : "auth.action.sign_in"])
                    .foregroundStyle(.secondary)
            } else {
                let lines = entry.summary?.lines ?? []
                if total == 0 {
                    Label(strings["ops.watch.all_clear"], systemImage: "checkmark")
                        .font(.headline)
                        .foregroundStyle(WatchPalette.clear)
                        .widgetAccentable()
                }
                let room = (total == 0 ? 2 : 3) - (age == nil ? 0 : 1)
                ForEach(lines.prefix(max(room, 0))) { line in
                    HStack(spacing: 4) {
                        Text(count(line.count))
                            .fontWeight(.bold)
                            .monospacedDigit()
                            .foregroundStyle(line.urgent ? WatchPalette.attention : .primary)
                            .widgetAccentable(line.urgent)
                        Text(strings[line.shortKey])
                            .lineLimit(1)
                    }
                }
                if let age {
                    Text(age)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var inlineText: String {
        guard entry.signedIn, entry.summary != nil else { return strings["ops.title"] }
        return total > 0 ? strings["ops.watch.need_attention", ["count": total]] : strings["ops.watch.all_clear"]
    }

    private var inline: some View {
        Label {
            Text(inlineText)
        } icon: {
            Image(systemName: total > 0 ? "exclamationmark.triangle.fill" : "checkmark")
        }
    }

    private var corner: some View {
        ZStack {
            AccessoryWidgetBackground()
            if entry.signedIn, entry.summary != nil, total > 0 {
                Text(count(total))
                    .font(.system(.title3, design: .rounded).weight(.bold))
                    .minimumScaleFactor(0.5)
                    .foregroundStyle(WatchPalette.attention)
                    .widgetAccentable()
            } else {
                Image(systemName: entry.signedIn && entry.summary != nil ? "checkmark" : "person.crop.circle.badge.questionmark")
                    .font(.title3.weight(.bold))
                    .widgetAccentable()
            }
        }
        .widgetLabel {
            Text(age ?? (total > 0 ? strings["admin.ops.attention"] : inlineText))
        }
    }
}
