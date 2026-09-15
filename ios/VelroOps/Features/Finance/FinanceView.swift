import SwiftUI
import VelroCore

/// Finance (admin/src/pages/Finance.tsx): the stored split over the last 7,
/// 30 or 90 days -- every figure as recorded, never recomputed from a rate
/// that may have changed since -- with the week's days from the dashboard.
struct FinanceView: View {
    @Environment(\.strings) private var strings

    init() {}

    var body: some View {
        FinanceScreen()
    }
}

private struct FinanceScreen: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @State private var model = FinanceModel()

    var body: some View {
        Group {
            if !ops.isFinance {
                EmptyStateView(messageKey: "error.permission_denied", systemImage: "lock")
            } else {
                content
            }
        }
        .background(Palette.background)
        .navigationTitle(strings["admin.nav.finance"])
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                RefreshButton { [model, ops] in await model.load(ops) }
            }
        }
        .poll(every: .seconds(300)) { [model, ops] in
            await model.load(ops)
        }
    }

    @ViewBuilder private var content: some View {
        @Bindable var bindable = model
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.s4) {
                Picker(strings["admin.col.period"], selection: $bindable.days) {
                    ForEach(FinanceModel.windows, id: \.self) { days in
                        Text(strings["admin.finance.period", ["days": days]]).tag(days)
                    }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                LoadStateView(model.current, retry: { [model, ops] in await model.load(ops) }) { summary in
                    FinanceBody(summary: summary, summaries: model.summaries, week: model.week)
                }
            }
            .padding(Spacing.s4)
            .frame(maxWidth: 1100, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .refreshable { [model, ops] in await model.load(ops) }
    }
}

@MainActor
@Observable
final class FinanceModel {
    static let windows = [7, 30, 90]

    var days = 30
    /// Every window at once: switching is instant, and the comparison chart
    /// needs all three.
    private(set) var summaries: [Int: FinanceSummary] = [:]
    private(set) var error: APIError?
    /// The last seven Kabul days, from the dashboard: the only per-day money
    /// the admin endpoints carry.
    private(set) var week: WeekHistory?

    var current: LoadState<FinanceSummary> {
        if let summary = summaries[days] { return .loaded(summary) }
        if let error { return .failed(error) }
        return .loading
    }

    func load(_ ops: OpsModel) async {
        async let seven = ops.send(AdminAPI.finance(days: 7))
        async let thirty = ops.send(AdminAPI.finance(days: 30))
        async let ninety = ops.send(AdminAPI.finance(days: 90))
        async let dashboard = ops.send(AdminAPI.dashboard())
        let results: [(Int, Result<FinanceSummary, APIError>)] = [(7, await seven), (30, await thirty), (90, await ninety)]
        var failure: APIError?
        for (window, result) in results {
            switch result {
            case .success(let summary): summaries[window] = summary
            case .failure(let error) where error != .cancelled: failure = error
            case .failure: break
            }
        }
        error = failure
        if case .success(let snapshot) = await dashboard { week = snapshot.history }
    }
}

private struct FinanceBody: View {
    let summary: FinanceSummary
    let summaries: [Int: FinanceSummary]
    let week: WeekHistory?
    @Environment(\.strings) private var strings

    /// Null when nothing was fared: that is not 0%.
    private var takeRate: Int? {
        guard summary.grossMinor > 0 else { return nil }
        return Int((Double(summary.platformMinor) * 100 / Double(summary.grossMinor)).rounded())
    }

    private var averageFare: Money {
        let count = Int64(max(summary.completedBookings, 1))
        return Money(amountMinor: summary.completedBookings > 0 ? summary.grossMinor / count : 0, currency: summary.currency)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s4) {
            HStack(spacing: Spacing.s1) {
                Image(systemName: "calendar")
                    .accessibilityHidden(true)
                DateText(summary.periodStart)
                Text("–")
                DateText(summary.periodEnd)
            }
            .opsFont(.label, weight: .regular)
            .foregroundStyle(Palette.textMuted)
            .accessibilityElement(children: .combine)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 170), spacing: Spacing.s3)], spacing: Spacing.s3) {
                StatCard("admin.finance.gross", money: summary.gross, systemImage: "banknote")
                StatCard("admin.finance.platform", money: summary.platform, systemImage: "building.columns")
                StatCard("admin.finance.driver", money: summary.driver, systemImage: "steeringwheel")
                StatCard("admin.finance.bookings", count: summary.completedBookings, systemImage: "checkmark.circle")
                StatCard("ops.finance.take_rate", percent: takeRate, systemImage: "percent")
                StatCard("ops.finance.average_fare", money: averageFare, systemImage: "equal.circle")
                StatCard("admin.finance.cash", money: summary.cash, systemImage: "banknote")
                StatCard("admin.finance.online", money: summary.online, systemImage: "iphone")
                StatCard("admin.finance.pending_settlement", money: summary.pendingSettlement, systemImage: "hourglass")
                StatCard("admin.finance.paid_settlement", money: summary.paidSettlement, systemImage: "checkmark.seal")
            }

            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 340), spacing: Spacing.s3, alignment: .top)],
                spacing: Spacing.s3
            ) {
                SplitChart(summary: summary)
                PaymentMethodChart(summary: summary)
                WindowCompareChart(summaries: summaries)
                if let week {
                    WeekFaresChart(history: week)
                }
            }
        }
    }
}
