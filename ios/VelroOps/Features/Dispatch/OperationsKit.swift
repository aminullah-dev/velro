import SwiftUI
import VelroCore

// The pieces the operations and directory screens share: dispatch, trips,
// live requests, bookings, drivers, vehicles, support and the audit log.
//
// Built here rather than in Design/ because this folder is the only one these
// screens own; each is general enough to move there (see the names prefixed
// `Op`), and nothing in it knows about a particular screen.

// MARK: - Paging

/// A list the server pages: the first page, the next ones as the reader
/// scrolls to the end, and a quiet refresh of everything already loaded.
///
///     @State private var pager = OpPager<AdminTrip>(pageSize: 50)
///     ...
///     await pager.reload { [ops] limit, offset in
///         await ops.sendWithMeta(AdminAPI.trips(TripFilter(limit: limit, offset: offset)))
///     }
///
/// A filter change is a `reload` with a new fetch: answers still in flight for
/// the old filter are dropped when they arrive, so a slow first page can never
/// land on top of the new one.
@MainActor
@Observable
final class OpPager<Item: Identifiable & Sendable> {
    typealias Fetch = @MainActor (_ limit: Int, _ offset: Int) async -> Result<Paged<[Item]>, APIError>

    private(set) var items: [Item] = []
    /// The server's count of every row the filter matches.
    private(set) var total: Int?
    private(set) var hasMore = false
    /// The first page failed and there is nothing to show.
    private(set) var error: APIError?
    /// A later page failed; what is loaded stays.
    private(set) var moreError: APIError?
    private(set) var isLoadingMore = false
    private(set) var hasLoaded = false

    let pageSize: Int
    private var fetch: Fetch?
    private var generation = 0
    /// Bumped by every page appended, so a refresh that started before one
    /// cannot land on top of it.
    private var appends = 0

    init(pageSize: Int = 50) { self.pageSize = pageSize }

    var isFirstLoad: Bool { !hasLoaded && error == nil }

    /// From the first page, with `fetch` from now on.
    func reload(_ fetch: @escaping Fetch) async {
        self.fetch = fetch
        generation += 1
        let mine = generation
        items = []
        total = nil
        hasMore = false
        error = nil
        moreError = nil
        hasLoaded = false
        isLoadingMore = false
        let result = await fetch(pageSize, 0)
        guard mine == generation else { return }
        switch result {
        case .success(let page):
            items = page.items
            total = page.meta.total
            hasMore = page.hasMore
            hasLoaded = true
        case .failure(let failure):
            if failure != .cancelled { error = failure }
        }
    }

    /// Everything already loaded, again -- for a poll or after an action --
    /// in one request of up to 200 rows. A failure keeps what is on screen.
    func refresh() async {
        // Before the first page there is nothing to refresh: the screen's own
        // first `reload` is on its way.
        guard let fetch, hasLoaded, !isLoadingMore else { return }
        let mine = generation
        let appended = appends
        let window = min(200, max(pageSize, items.count))
        let result = await fetch(window, 0)
        // A page appended meanwhile makes this answer the older of the two.
        guard mine == generation, appended == appends, !isLoadingMore else { return }
        guard case .success(let page) = result else { return }
        total = page.meta.total
        if items.count > window {
            // More is loaded than one request can refresh: the first rows are
            // renewed and the rest kept, so the list never shrinks under the
            // reader's thumb.
            let fresh = Set(page.items.map(\.id))
            items = page.items + items.dropFirst(window).filter { !fresh.contains($0.id) }
        } else {
            items = page.items
            hasMore = page.hasMore
        }
    }

    /// The next page, when the reader reaches the end of this one.
    func loadMore() async {
        guard let fetch, hasLoaded, hasMore, !isLoadingMore else { return }
        let mine = generation
        isLoadingMore = true
        moreError = nil
        let result = await fetch(pageSize, items.count)
        guard mine == generation else { return }
        isLoadingMore = false
        switch result {
        case .success(let page):
            // A row that moved between pages while the reader scrolled is
            // shown once, where it was first seen.
            let seen = Set(items.map(\.id))
            items += page.items.filter { !seen.contains($0.id) }
            total = page.meta.total
            hasMore = page.hasMore
            appends += 1
        case .failure(let failure):
            if failure != .cancelled { moreError = failure }
        }
    }
}

/// The end of a paged list: fetches the next page when it scrolls into view,
/// a spinner while it comes, a retry if it failed, and "Showing 1–50 of 312".
struct OpPagerFooter<Item: Identifiable & Sendable>: View {
    @Environment(\.strings) private var strings
    let pager: OpPager<Item>

    var body: some View {
        VStack(spacing: Spacing.s2) {
            if let error = pager.moreError {
                Text(strings.forErrorCode(error.code, context: error.context.arguments))
                    .opsFont(.caption)
                    .foregroundStyle(Palette.danger)
                Button(strings["common.action.retry"]) {
                    Task { await pager.loadMore() }
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            } else if pager.hasMore {
                ProgressView()
                    .controlSize(.small)
                    .onAppear { Task { await pager.loadMore() } }
            }
            if let total = pager.total, total > 0, !pager.items.isEmpty {
                Text(strings["admin.showing", [
                    "from": 1, "to": pager.items.count, "total": total,
                ]])
                .opsFont(.caption)
                .foregroundStyle(Palette.textMuted)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, Spacing.s2)
        .listRowSeparator(.hidden)
    }
}

// MARK: - List beside its detail

/// Whether a screen has room for its list and the selected row side by side:
/// always on the Mac, on an iPad in a regular-width window, never on an iPhone.
struct OpSplitReader<Content: View>: View {
    #if os(iOS)
    @Environment(\.horizontalSizeClass) private var sizeClass
    #endif
    @ViewBuilder let content: (_ isSplit: Bool) -> Content

    var body: some View {
        #if os(iOS)
        content(sizeClass == .regular)
        #else
        content(true)
        #endif
    }
}

/// A list on the leading side and the selected row's detail beside it. The
/// list keeps the width a row needs; the detail takes the rest.
struct OpSplitLayout<ListContent: View, Detail: View>: View {
    private let listWidth: CGFloat
    private let list: ListContent
    private let detail: Detail

    init(listWidth: CGFloat = 400, @ViewBuilder list: () -> ListContent, @ViewBuilder detail: () -> Detail) {
        self.listWidth = listWidth
        self.list = list()
        self.detail = detail()
    }

    var body: some View {
        HStack(spacing: 0) {
            list
                .frame(minWidth: 300, idealWidth: listWidth, maxWidth: listWidth)
            Divider()
            detail
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Palette.background)
                .environment(\.opInSplitDetail, true)
        }
    }
}

extension EnvironmentValues {
    /// Inside `OpSplitLayout`'s detail pane, where the screen keeps its own
    /// title: a detail sets one only when it was pushed on its own.
    @Entry var opInSplitDetail = false
}

extension View {
    /// The title of a detail screen pushed on its own; beside its list, the
    /// list's screen keeps its title.
    func opNavigationTitle(_ title: String) -> some View {
        modifier(OpDetailNavigationTitle(title: title))
    }
}

private struct OpDetailNavigationTitle: ViewModifier {
    @Environment(\.opInSplitDetail) private var inSplit
    let title: String

    @ViewBuilder
    func body(content: Content) -> some View {
        if inSplit {
            content
        } else {
            content.navigationTitle(title)
        }
    }
}

/// The detail pane with nothing chosen yet.
struct OpNothingSelected: View {
    @Environment(\.strings) private var strings
    let messageKey: String
    var systemImage = "sidebar.left"

    var body: some View {
        EmptyStateView(messageKey: messageKey, systemImage: systemImage)
    }
}

// MARK: - Filters

/// A row of filters as pills, the panel's `.filters`: one chosen at a time,
/// scrolling sideways when they do not fit. Each says in words whether it is
/// on, for VoiceOver.
struct OpChipBar<Value: Hashable>: View {
    struct Option: Identifiable {
        let value: Value
        let label: String
        var count: Int?
        var id: Value { value }
    }

    @Environment(\.strings) private var strings
    let options: [Option]
    @Binding var selection: Value

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: Spacing.s2) {
                ForEach(options) { option in
                    let isOn = option.value == selection
                    Button {
                        selection = option.value
                    } label: {
                        HStack(spacing: Spacing.s1) {
                            Text(option.label)
                            if let count = option.count, count > 0 {
                                Text(OpsFormat.count(count, strings))
                                    .monospacedDigit()
                                    .padding(.horizontal, 6)
                                    .background(isOn ? Palette.onAccent.opacity(0.2) : Palette.border, in: Capsule())
                            }
                        }
                        .opsFont(.label, weight: isOn ? .medium : .regular)
                        .padding(.horizontal, Spacing.s3)
                        .padding(.vertical, 6)
                        .foregroundStyle(isOn ? Palette.onAccent : Palette.text)
                        .background(isOn ? Palette.accent : Palette.surfaceMuted, in: Capsule())
                        .overlay { Capsule().strokeBorder(isOn ? Color.clear : Palette.border, lineWidth: 1) }
                        .contentShape(Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityAddTraits(isOn ? [.isSelected] : [])
                    .accessibilityIdentifier("chip." + String(describing: option.value))
                }
            }
            .padding(.horizontal, Spacing.s4)
            .padding(.vertical, Spacing.s2)
        }
    }
}

// MARK: - Toolbar

/// Refresh, with ⌘R on a keyboard, spinning while it works.
struct OpRefreshButton: View {
    @Environment(\.strings) private var strings
    let action: @MainActor () async -> Void
    @State private var isWorking = false

    var body: some View {
        Button {
            Task {
                isWorking = true
                await action()
                isWorking = false
            }
        } label: {
            if isWorking {
                ProgressView().controlSize(.small)
            } else {
                Label(strings["admin.action.refresh"], systemImage: "arrow.clockwise")
            }
        }
        .disabled(isWorking)
        .keyboardShortcut("r", modifiers: .command)
        .help(strings["admin.action.refresh"])
    }
}

// MARK: - Words and figures

enum OpText {
    /// "in 45 min", "in 2 h 10 min", "12 min ago": how far a departure is.
    static func untilDeparture(minutes: Int, _ strings: Strings) -> String {
        let magnitude = abs(minutes)
        if minutes < 0 { return strings["admin.dispatch.minutes_ago", ["minutes": magnitude]] }
        if magnitude < 60 { return strings["admin.dispatch.in_minutes", ["minutes": magnitude]] }
        return strings["admin.dispatch.in_hours", ["hours": magnitude / 60, "minutes": magnitude % 60]]
    }

    /// "Khishki → Charikar", with the arrow the reader's language points.
    ///
    /// Each name is its own bidi isolate. Place names are Dari even in the
    /// English console; left bare, "خیشکی → چاریکار" is laid out right to
    /// left as one run and the unmirrored arrow then points from Charikar to
    /// Khishki -- the trip backwards.
    static func route(_ origin: String?, _ destination: String?, _ strings: Strings) -> String {
        strings["admin.map.route", [
            "origin": "\u{2068}\(origin ?? "—")\u{2069}",
            "destination": "\u{2068}\(destination ?? "—")\u{2069}",
        ]]
    }

    /// "2 / 4": seats taken of the car's seats.
    static func seats(booked: Int, capacity: Int, _ strings: Strings) -> String {
        OpsFormat.count(booked, strings) + " / " + OpsFormat.count(capacity, strings)
    }

    /// "★ 4.6 (12)", or "No ratings yet".
    static func rating(_ average: Double?, count: Int, _ strings: Strings) -> String {
        // Not the driver app's "No ratings yet": in Dari and Pashto that one
        // speaks to the driver himself ("you have not been rated").
        guard let average, count > 0 else { return strings["ops.drivers.no_rating"] }
        let value = Numerals.localise(String(format: "%.1f", average), strings.locale)
        return "★ \(value) (\(OpsFormat.count(count, strings)))"
    }

    /// "★ 4.6" alone, where no count comes with it; "No ratings yet".
    static func stars(_ average: Double?, _ strings: Strings) -> String {
        guard let average else { return strings["ops.drivers.no_rating"] }
        return "★ " + Numerals.localise(String(format: "%.1f", average), strings.locale)
    }

    /// A name, or the panel's "No name given".
    static func name(_ name: String?, _ strings: Strings) -> String {
        guard let name, !name.trimmingCharacters(in: .whitespaces).isEmpty else { return strings["common.value.no_name"] }
        return name
    }

    /// A key's sentence, or the raw code when the files have none -- a
    /// visible gap rather than a blank.
    static func word(_ key: String, raw: String, _ strings: Strings) -> String {
        strings.has(key) ? strings[key] : raw
    }

    static func rideKind(_ code: String, _ strings: Strings) -> String {
        word("ride.kind." + code.lowercased(), raw: code, strings)
    }

    static func vehicleType(_ code: String, _ strings: Strings) -> String {
        word("vehicle_type." + code.lowercased(), raw: code, strings)
    }

    static func role(_ code: String, _ strings: Strings) -> String {
        word("role." + code.lowercased(), raw: code, strings)
    }

    static func error(_ error: APIError, _ strings: Strings) -> String {
        strings.forErrorCode(error.code, context: error.context.arguments)
    }
}

// MARK: - Detail panes

/// A label and its value on one line of a detail pane; the value may be
/// selected and copied.
struct OpField<Value: View>: View {
    @Environment(\.strings) private var strings
    private let labelKey: String
    private let value: Value

    init(_ labelKey: String, @ViewBuilder value: () -> Value) {
        self.labelKey = labelKey
        self.value = value()
    }

    var body: some View {
        LabeledContent {
            value
                .opsFont(.body)
                .foregroundStyle(Palette.text)
                .multilineTextAlignment(.trailing)
                .textSelection(.enabled)
        } label: {
            Text(strings[labelKey])
                .opsFont(.label, weight: .regular)
                .foregroundStyle(Palette.textMuted)
        }
        .accessibilityElement(children: .combine)
    }
}

extension OpField where Value == Text {
    init(_ labelKey: String, text: String) {
        self.init(labelKey) { Text(text) }
    }
}

/// A section title inside a `Form`, in the console's type.
struct OpFormHeader: View {
    @Environment(\.strings) private var strings
    let titleKey: String

    var body: some View {
        Text(strings[titleKey])
            .opsFont(.label, weight: .medium)
            .foregroundStyle(Palette.textMuted)
            .accessibilityAddTraits(.isHeader)
    }
}

/// The header block of a detail pane: a big identifier and its chips.
struct OpDetailTitle<Chips: View>: View {
    let title: String
    let subtitle: String?
    let isLatin: Bool
    let chips: Chips

    init(_ title: String, subtitle: String? = nil, isLatin: Bool = false, @ViewBuilder chips: () -> Chips) {
        self.title = title
        self.subtitle = subtitle
        self.isLatin = isLatin
        self.chips = chips()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s2) {
            Group {
                if isLatin { LTRText(title) } else { Text(title) }
            }
            .opsFont(.headline, weight: .bold)
            .foregroundStyle(Palette.text)
            .textSelection(.enabled)
            if let subtitle {
                Text(subtitle)
                    .opsFont(.body)
                    .foregroundStyle(Palette.textMuted)
            }
            HStack(spacing: Spacing.s2) { chips }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Rows

extension View {
    /// The dispatcher's at-risk tint on a row (tbody tr.at-risk), with a
    /// thick start edge so it survives a colour-blind reading.
    func opAttentionRow(_ on: Bool) -> some View {
        listRowBackground(
            on ? AnyView(
                Palette.atRisk.overlay(alignment: .leading) {
                    Rectangle().fill(Palette.attentionEdge).frame(width: 4)
                }
            ) : nil
        )
    }
}
