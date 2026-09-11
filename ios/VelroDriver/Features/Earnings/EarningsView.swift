import Charts
import Observation
import SwiftUI
import VelroCore

@MainActor
@Observable
final class EarningsModel {
    enum Period: String, CaseIterable { case day, week, month
        /// How many bars each period shows: two weeks of days, a quarter of
        /// weeks, a year of months.
        var buckets: Int { self == .day ? 14 : 12 }
    }

    private(set) var earnings: Earnings?
    private(set) var summary: EarningsSummary?
    private(set) var entries: [LedgerEntry] = []
    private(set) var hasMore = false
    private(set) var ledgerFailed = false
    private(set) var payouts: PayoutOptions?
    private(set) var isLoading = true
    private(set) var error: APIError?
    private(set) var period: Period = .day

    private let app: AppModel
    private var nextOffset = 0

    init(app: AppModel) {
        self.app = app
        earnings = app.personal.value(Earnings.self, key: "driver-earnings")
    }

    func load() async {
        let money = await app.client.send(API.earnings(), caching: "driver-earnings", in: app.personal)
        if let value = money.value { earnings = value }
        error = earnings == nil ? money.error : nil
        await loadSummary(period)
        if case .success(let options) = await app.client.send(API.payoutOptions()) { payouts = options }
        await loadLedger(reset: true)
        isLoading = false
    }

    func choose(_ period: Period) async {
        guard period != self.period else { return }
        self.period = period
        await loadSummary(period)
    }

    private func loadSummary(_ period: Period) async {
        let result = await app.client.send(API.earningsSummary(period: period.rawValue, buckets: period.buckets))
        // A slow answer for a tab he has already left must not overwrite the one he is on.
        guard self.period == period else { return }
        if case .success(let fresh) = result { summary = fresh }
    }

    func loadLedger(reset: Bool = false) async {
        if reset { nextOffset = 0 }
        switch await app.client.send(API.ledger(limit: 30, offset: nextOffset)) {
        case .success(let page):
            let fetched = page.entries ?? []
            entries = reset ? fetched : entries + fetched
            hasMore = page.hasMore == true
            nextOffset = page.nextOffset ?? (nextOffset + fetched.count)
            ledgerFailed = false
        case .failure(let failure):
            if failure != .cancelled { ledgerFailed = true }
        }
    }
}

struct EarningsView: View {
    @Environment(\.strings) private var strings
    @State private var model: EarningsModel

    init(app: AppModel) {
        _model = State(initialValue: EarningsModel(app: app))
    }

    var body: some View {
        VelroScreen(title: strings["driver.earnings.title"]) {
            ScrollView {
                VStack(alignment: .leading, spacing: Spacing.md) {
                    if let earnings = model.earnings {
                        balance(earnings)
                        chart
                        payouts
                        ledger
                    } else if model.isLoading {
                        LoadingState()
                    } else if let error = model.error {
                        ErrorState(error: error) { Task { await model.load() } }
                    }
                }
                .padding(.horizontal, Spacing.gutter)
                .padding(.vertical, Spacing.md)
            }
            .refreshable { await model.load() }
        }
        .task { await model.load() }
    }

    private func balance(_ earnings: Earnings) -> some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.sm) {
                Text(strings[earnings.owes ? "driver.earnings.owed" : "driver.earnings.available"])
                    .velroFont(.label)
                    .foregroundStyle(Palette.onSurfaceVariant)
                Text(MoneyFormatter.format(earnings.headline, strings: strings))
                    .velroFont(.display, weight: .bold)
                    .foregroundStyle(earnings.owes ? Palette.error : Palette.primary)
                if earnings.owes {
                    Text(strings["driver.earnings.owed_explained"])
                        .velroFont(.caption)
                        .foregroundStyle(Palette.onSurfaceVariant)
                    Text(strings["driver.earnings.settle_at_station"])
                        .velroFont(.label, weight: .medium)
                        .foregroundStyle(Palette.onSurface)
                }
                // Both buckets, so a debt or a payout on its way to the
                // office is never money that seems to have gone missing.
                if earnings.pending.amountMinor != 0 {
                    row("earnings.label.available", MoneyFormatter.format(minor: earnings.available.amountMinor, currency: earnings.available.currency, strings: strings, showPlus: true))
                    row("driver.earnings.pending", MoneyFormatter.format(minor: earnings.pending.amountMinor, currency: earnings.pending.currency, strings: strings, showPlus: true))
                }
                Divider()
                row("driver.earnings.lifetime_earned", MoneyFormatter.format(earnings.lifetimeEarned, strings: strings))
                row("driver.earnings.lifetime_commission", MoneyFormatter.format(earnings.lifetimeCommission, strings: strings))
                if let paid = earnings.lifetimePaid {
                    row("driver.earnings.lifetime_paid", MoneyFormatter.format(paid, strings: strings))
                }
                row("driver.earnings.trips", Numerals.localise(String(earnings.completedTrips), strings.locale))
            }
        }
    }

    private var chart: some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.md) {
                Picker("", selection: Binding(get: { model.period }, set: { period in Task { await model.choose(period) } })) {
                    ForEach(EarningsModel.Period.allCases, id: \.self) { period in
                        Text(strings["driver.earnings.period.\(period.rawValue)"]).tag(period)
                    }
                }
                .pickerStyle(.segmented)
                let buckets = model.summary?.buckets ?? []
                if !buckets.isEmpty {
                    let total = buckets.reduce(Int64(0)) { $0 + $1.net.amountMinor }
                    let trips = buckets.reduce(0) { $0 + ($1.trips ?? 0) }
                    Text(strings["driver.earnings.chart_summary", [
                        "total": MoneyFormatter.format(Money(amountMinor: total, currency: buckets[0].net.currency), strings: strings),
                        "trips": Numerals.localise(String(trips), strings.locale),
                    ]])
                    .velroFont(.label, weight: .medium)
                    .foregroundStyle(Palette.onSurface)
                    Chart(buckets) { bucket in
                        BarMark(
                            // Labelled in the calendar the rest of the app
                            // speaks: Shamsi in Dari and Pashto.
                            x: .value("", label(bucket)),
                            y: .value("", Double(bucket.net.amountMinor) / 100)
                        )
                        .foregroundStyle(Palette.primary)
                    }
                    .chartYAxis { AxisMarks(position: .leading) }
                    .frame(height: 180)
                    .environment(\.layoutDirection, .leftToRight)
                    .accessibilityHidden(true)
                }
            }
        }
    }

    private func label(_ bucket: EarningsBucket) -> String {
        guard let start = bucket.start else { return bucket.startsOn }
        let shamsi = Calendars.shamsi(start)
        switch model.period {
        case .month:
            return strings.locale == .english
                ? start.formatted(.dateTime.month(.abbreviated))
                : Numerals.localise(String(shamsi.month), strings.locale)
        case .day, .week:
            return strings.locale == .english
                ? start.formatted(.dateTime.day().month(.defaultDigits))
                : Numerals.localise("\(shamsi.month)/\(shamsi.day)", strings.locale)
        }
    }

    @ViewBuilder
    private var payouts: some View {
        if let open = model.payouts?.openReference {
            Text(strings["driver.earnings.open_request", ["reference": open]])
                .velroFont(.label, weight: .medium)
                .foregroundStyle(Palette.accent)
        }
        let settled = model.payouts?.settlements ?? []
        if !settled.isEmpty {
            Text(strings["driver.earnings.history"])
                .velroFont(.heading, weight: .medium)
                .foregroundStyle(Palette.onSurface)
                .padding(.top, Spacing.sm)
            ForEach(settled) { settlement in
                HStack {
                    VStack(alignment: .leading, spacing: Spacing.xxs) {
                        Text(settlement.reference)
                            .velroFont(.label)
                            .foregroundStyle(Palette.onSurface)
                            .environment(\.layoutDirection, .leftToRight)
                        StatusChip(key: "settlement.status.\(settlement.status.rawValue.lowercased())",
                                   tone: settlement.status == .paid ? .ended : settlement.status == .rejected ? .failed : .attention)
                    }
                    Spacer()
                    Text(MoneyFormatter.format(settlement.amount, strings: strings))
                        .velroFont(.heading, weight: .medium)
                        .foregroundStyle(Palette.onSurface)
                }
                .padding(.vertical, Spacing.xs)
            }
        }
    }

    @ViewBuilder
    private var ledger: some View {
        Text(strings["driver.earnings.ledger"])
            .velroFont(.heading, weight: .medium)
            .foregroundStyle(Palette.onSurface)
            .padding(.top, Spacing.sm)
        if model.ledgerFailed && model.entries.isEmpty {
            Button { Task { await model.loadLedger(reset: true) } } label: {
                Text(strings["driver.earnings.ledger_failed"])
                    .velroFont(.label)
                    .foregroundStyle(Palette.error)
            }
        } else if model.entries.isEmpty {
            Text(strings["driver.earnings.ledger_empty"])
                .velroFont(.label)
                .foregroundStyle(Palette.onSurfaceVariant)
        } else {
            LazyVStack(spacing: 0) {
                ForEach(model.entries) { entry in
                    LedgerRow(entry: entry)
                    Divider()
                }
            }
            if model.hasMore {
                SecondaryButton(label: strings["driver.earnings.load_more"]) { Task { await model.loadLedger() } }
            }
        }
    }

    private func row(_ key: String, _ value: String) -> some View {
        HStack {
            Text(strings[key]).velroFont(.label).foregroundStyle(Palette.onSurfaceVariant)
            Spacer()
            Text(value).velroFont(.label, weight: .medium).foregroundStyle(Palette.onSurface)
        }
    }
}

private struct LedgerRow: View {
    let entry: LedgerEntry
    @Environment(\.strings) private var strings

    var body: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: Spacing.xxs) {
                Text(strings["ledger.kind.\(entry.kind.lowercased())"])
                    .velroFont(.label, weight: .medium)
                    .foregroundStyle(Palette.onSurface)
                if let created = entry.created {
                    Text(Calendars.dateTime(created, strings.locale))
                        .velroFont(.caption)
                        .foregroundStyle(Palette.onSurfaceVariant)
                }
            }
            Spacer()
            VStack(alignment: .trailing, spacing: Spacing.xxs) {
                Text(MoneyFormatter.format(minor: entry.amount.amountMinor, currency: entry.amount.currency, strings: strings, showPlus: true))
                    .velroFont(.label, weight: .bold)
                    .foregroundStyle(entry.amount.amountMinor < 0 ? Palette.error : Palette.primary)
                Text(strings["driver.earnings.balance_after", ["amount": MoneyFormatter.format(entry.balanceAfter, strings: strings)]])
                    .velroFont(.caption)
                    .foregroundStyle(Palette.onSurfaceVariant)
            }
        }
        .padding(.vertical, Spacing.sm)
    }
}
