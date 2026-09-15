import SwiftUI
import VelroCore

/// The dashboard as vertical pages: attention first, then now, today, the
/// drivers, the passengers, and the language.
struct DashboardView: View {
    @Environment(WatchModel.self) private var model

    var body: some View {
        NavigationStack {
            TabView {
                if let snapshot = model.snapshot, !model.noDashboard {
                    AttentionPage(snapshot: snapshot)
                    CountsPage(titleKey: "admin.ops.now", rows: [
                        CountRow("admin.stat.on_the_way", snapshot.live.onTheWay),
                        CountRow("admin.stat.at_the_station", snapshot.live.atTheStation),
                        CountRow("admin.stat.moving", snapshot.live.moving),
                        CountRow("admin.stat.departing_soon", snapshot.live.departingSoon),
                    ])
                    CountsPage(titleKey: "admin.ops.today", rows: todayRows(snapshot.today))
                    CountsPage(titleKey: "admin.nav.drivers", rows: [
                        CountRow("admin.stat.drivers_online", snapshot.drivers.online),
                        CountRow("admin.stat.drivers_on_trip", snapshot.drivers.onTrip),
                        CountRow("admin.stat.drivers_offline", snapshot.drivers.offline),
                        CountRow("admin.stat.stale_gps", snapshot.drivers.withoutFix, urgent: true),
                    ])
                    // Only from a server that sends the block.
                    if let passengers = snapshot.passengers {
                        CountsPage(titleKey: "admin.stat.passengers", rows: [
                            CountRow("ops.passengers.stat.new_today", passengers.newToday),
                            CountRow("ops.passengers.stat.active_7d", passengers.active7d),
                            CountRow("admin.stat.passengers_with_request", passengers.withOpenRequest),
                        ])
                    }
                } else {
                    WaitingPage()
                }
                SettingsPage()
            }
            .tabViewStyle(.verticalPage)
        }
    }

    private func todayRows(_ t: DashboardSnapshot.Today) -> [CountRow] {
        let strings = model.strings
        return [
            CountRow("admin.stat.trips_today", t.trips),
            CountRow("admin.stat.bookings_today", t.bookings),
            CountRow("admin.stat.completed_today", t.completedTrips),
            CountRow("admin.stat.cancellations_today", t.cancellations),
            CountRow("admin.stat.utilisation", text: WatchFormat.fraction(t.seatsSold, of: t.seatsCapacity, strings)),
        ]
    }
}

// MARK: - Attention

/// The total, amber when anything waits, then only what is not zero.
private struct AttentionPage: View {
    @Environment(WatchModel.self) private var model
    let snapshot: DashboardSnapshot

    var body: some View {
        let strings = model.strings
        let total = AttentionSummary.total(snapshot)
        let lines = AttentionSummary.lines(snapshot)
        List {
            VStack(alignment: .leading, spacing: 0) {
                Text(WatchFormat.count(total, strings))
                    .font(.system(size: 44, weight: .bold, design: .rounded))
                    .monospacedDigit()
                    .foregroundStyle(total > 0 ? WatchPalette.attention : WatchPalette.clear)
                Text(strings[total > 0 ? "admin.ops.attention" : "admin.ops.all_clear"])
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .listRowBackground(Color.clear)
            .accessibilityElement(children: .combine)

            ForEach(lines) { line in
                CountRowView(row: CountRow(line.key, line.count, urgent: line.urgent))
            }
            StatusLine()
        }
        .navigationTitle(strings["ops.title"])
        .toolbar { RefreshButton() }
        .containerBackground(for: .tabView) {
            if total > 0 {
                LinearGradient(colors: [WatchPalette.amber.opacity(0.45), .clear], startPoint: .top, endPoint: .bottom)
            } else {
                Color.clear
            }
        }
    }
}

// MARK: - A page of counts

struct CountRow: Identifiable {
    let key: String
    let value: String?
    let count: Int
    let urgent: Bool
    var id: String { key }

    init(_ key: String, _ count: Int, urgent: Bool = false) {
        self.key = key
        self.count = count
        self.value = nil
        self.urgent = urgent
    }

    /// A figure already written, such as seats sold of seats.
    init(_ key: String, text: String) {
        self.key = key
        self.count = 0
        self.value = text
        self.urgent = false
    }
}

private struct CountsPage: View {
    @Environment(WatchModel.self) private var model
    let titleKey: String
    let rows: [CountRow]

    var body: some View {
        List {
            ForEach(rows) { row in CountRowView(row: row) }
            StatusLine()
        }
        .navigationTitle(model.strings[titleKey])
        .toolbar { RefreshButton() }
    }
}

/// A label and its number, the number at the trailing edge.
private struct CountRowView: View {
    @Environment(WatchModel.self) private var model
    let row: CountRow

    var body: some View {
        let strings = model.strings
        HStack(alignment: .center, spacing: 6) {
            Text(strings[row.key])
                .font(.footnote)
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 4)
            Text(row.value ?? WatchFormat.count(row.count, strings))
                .font(.title3.weight(.semibold))
                .monospacedDigit()
                .foregroundStyle(row.urgent && row.count > 0 ? WatchPalette.attention : .primary)
        }
        .accessibilityElement(children: .combine)
    }
}

// MARK: - When the figures are, and are not

/// "Updated 14:05", or how old the figures are when the last read failed.
private struct StatusLine: View {
    @Environment(WatchModel.self) private var model

    var body: some View {
        TimelineView(.periodic(from: .now, by: 30)) { context in
            let strings = model.strings
            Group {
                if let asOf = model.asOf {
                    if model.lastError != nil {
                        Text(strings["ops.watch.stale", ["age": WatchFormat.age(since: asOf, now: context.date, strings)]])
                            .foregroundStyle(WatchPalette.attention)
                    } else {
                        Text(strings["ops.watch.updated", ["time": Calendars.time(asOf, strings.locale)]])
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .font(.caption2)
            .fixedSize(horizontal: false, vertical: true)
        }
        .listRowBackground(Color.clear)
    }
}

private struct RefreshButton: ToolbarContent {
    @Environment(WatchModel.self) private var model

    var body: some ToolbarContent {
        ToolbarItem(placement: .topBarTrailing) {
            Button {
                Task { await model.refresh() }
            } label: {
                // The button wears the app's amber; its glyph in the same
                // amber vanished into it. Dark ink reads on amber.
                if model.isRefreshing {
                    ProgressView().tint(.black)
                } else {
                    Image(systemName: "arrow.clockwise")
                        .foregroundStyle(.black)
                }
            }
            .disabled(model.isRefreshing)
            .accessibilityLabel(model.strings["admin.action.refresh"])
        }
    }
}

/// Nothing to show yet: loading, the reason the first read failed, or a
/// role without the dashboard.
private struct WaitingPage: View {
    @Environment(WatchModel.self) private var model

    var body: some View {
        let strings = model.strings
        ScrollView {
            VStack(spacing: 10) {
                if model.noDashboard {
                    Image(systemName: "lock")
                        .font(.title3)
                        .foregroundStyle(.secondary)
                        .accessibilityHidden(true)
                    Text(strings["ops.watch.no_dashboard"])
                        .font(.footnote)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                } else if let error = model.lastError {
                    Text(strings.forErrorCode(error.code, context: error.context.arguments))
                        .font(.footnote)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                    Button(strings["common.action.retry"]) {
                        Task { await model.refresh() }
                    }
                    .disabled(model.isRefreshing)
                } else {
                    ProgressView()
                    Text(strings["common.state.loading"])
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .frame(maxWidth: .infinity)
        }
        .navigationTitle(strings["ops.title"])
    }
}
