import Charts
import SwiftUI
import VelroCore

// The finance charts. FinanceSummary carries totals for a window, so the
// charts show how those totals divide and how the windows compare; the one
// per-day series the admin endpoints carry is the dashboard's last seven days.

/// A chart with its title, on a card.
struct ChartCard<Content: View>: View {
    let title: String
    var subtitle: String?
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s3) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .opsFont(.heading, weight: .bold)
                    .foregroundStyle(Palette.text)
                    .accessibilityAddTraits(.isHeader)
                if let subtitle {
                    Text(subtitle)
                        .opsFont(.caption)
                        .foregroundStyle(Palette.textMuted)
                }
            }
            content
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .opsCard()
    }
}

enum ChartMoney {
    /// Afghani, for plotting. Labels are written with `OpsFormat`, never from this.
    static func afghani(_ minor: Int64) -> Double { Double(minor) / 100 }

    /// An axis figure in the reader's digits, whole afghani.
    static func axis(_ value: Double, _ strings: Strings) -> String {
        OpsFormat.count(Int(value.rounded()), strings)
    }

    static func percent(_ part: Int64, of whole: Int64, _ strings: Strings) -> String {
        guard whole > 0 else { return OpsFormat.percent(nil, strings) }
        return OpsFormat.percent(Int((Double(part) * 100 / Double(whole)).rounded()), strings)
    }
}

private struct EmptyChartNote: View {
    @Environment(\.strings) private var strings

    var body: some View {
        Text(strings["ops.finance.empty"])
            .opsFont(.body)
            .foregroundStyle(Palette.textMuted)
            .frame(maxWidth: .infinity, minHeight: 120)
    }
}

// MARK: - Where the fares went

struct SplitChart: View {
    let summary: FinanceSummary
    @Environment(\.strings) private var strings

    private struct Slice: Identifiable {
        let key: String
        let minor: Int64
        let color: Color
        var id: String { key }
    }

    private var slices: [Slice] {
        [
            Slice(key: "admin.finance.platform", minor: max(summary.platformMinor, 0), color: Palette.accent),
            Slice(key: "admin.finance.driver", minor: max(summary.driverMinor, 0), color: Palette.attention),
        ]
    }

    var body: some View {
        ChartCard(title: strings["ops.finance.split_title"]) {
            if summary.grossMinor <= 0 {
                EmptyChartNote()
            } else {
                HStack(spacing: Spacing.s4) {
                    Chart(slices) { slice in
                        SectorMark(
                            angle: .value(strings["admin.col.amount"], ChartMoney.afghani(slice.minor)),
                            innerRadius: .ratio(0.64),
                            angularInset: 1.5
                        )
                        .foregroundStyle(slice.color)
                        .cornerRadius(3)
                        .accessibilityLabel(strings[slice.key])
                        .accessibilityValue(OpsFormat.money(minor: slice.minor, currency: summary.currency, strings: strings))
                    }
                    .chartLegend(.hidden)
                    .chartBackground { proxy in
                        GeometryReader { geometry in
                            if let anchor = proxy.plotFrame {
                                let frame = geometry[anchor]
                                VStack(spacing: 0) {
                                    Text(strings["admin.finance.gross"])
                                        .opsFont(.caption)
                                        .foregroundStyle(Palette.textMuted)
                                    Text(OpsFormat.money(summary.gross, strings: strings))
                                        .opsFont(.label, weight: .bold)
                                        .foregroundStyle(Palette.text)
                                        .lineLimit(1)
                                        .minimumScaleFactor(0.5)
                                }
                                .frame(width: frame.width * 0.56)
                                .position(x: frame.midX, y: frame.midY)
                            }
                        }
                    }
                    .frame(width: 168, height: 168)

                    VStack(alignment: .leading, spacing: Spacing.s3) {
                        ForEach(slices) { slice in
                            legendRow(slice)
                        }
                    }
                    Spacer(minLength: 0)
                }
            }
        }
    }

    private func legendRow(_ slice: Slice) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: Spacing.s2) {
            Circle().fill(slice.color).frame(width: 10, height: 10)
            VStack(alignment: .leading, spacing: 2) {
                Text(strings[slice.key])
                    .opsFont(.label, weight: .regular)
                    .foregroundStyle(Palette.textMuted)
                MoneyText(minor: slice.minor, currency: summary.currency)
                    .opsFont(.heading, weight: .bold)
                    .foregroundStyle(Palette.text)
                Text(ChartMoney.percent(slice.minor, of: summary.grossMinor, strings))
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
            }
        }
        .accessibilityElement(children: .combine)
    }
}

// MARK: - How passengers paid

struct PaymentMethodChart: View {
    let summary: FinanceSummary
    @Environment(\.strings) private var strings

    private struct Row: Identifiable {
        let key: String
        let minor: Int64
        let color: Color
        var id: String { key }
    }

    private var rows: [Row] {
        [
            Row(key: "admin.finance.cash", minor: max(summary.cashMinor, 0), color: Palette.attention),
            Row(key: "admin.finance.online", minor: max(summary.onlineMinor, 0), color: Palette.accent),
        ]
    }

    var body: some View {
        let top = max(ChartMoney.afghani(rows.map(\.minor).max() ?? 0), 1)
        ChartCard(title: strings["ops.finance.method_title"]) {
            if summary.cashMinor <= 0 && summary.onlineMinor <= 0 {
                EmptyChartNote()
            } else {
                Chart(rows) { row in
                    BarMark(
                        x: .value(strings["admin.col.amount"], ChartMoney.afghani(row.minor)),
                        y: .value(strings["admin.col.type"], strings[row.key])
                    )
                    .foregroundStyle(row.color)
                    .cornerRadius(4)
                    .annotation(position: .trailing, alignment: .leading) {
                        VStack(alignment: .leading, spacing: 0) {
                            Text(OpsFormat.money(minor: row.minor, currency: summary.currency, strings: strings))
                                .opsFont(.caption, weight: .medium)
                                .foregroundStyle(Palette.text)
                            Text(ChartMoney.percent(row.minor, of: summary.cashMinor + summary.onlineMinor, strings))
                                .opsFont(.caption)
                                .foregroundStyle(Palette.textMuted)
                        }
                    }
                    .accessibilityLabel(strings[row.key])
                    .accessibilityValue(OpsFormat.money(minor: row.minor, currency: summary.currency, strings: strings))
                }
                .chartXScale(domain: 0...(top * 1.6))
                .chartXAxis(.hidden)
                .chartYAxis {
                    AxisMarks { value in
                        AxisValueLabel {
                            if let label = value.as(String.self) {
                                Text(label).opsFont(.caption)
                            }
                        }
                    }
                }
                .frame(height: 120)
            }
        }
    }
}

// MARK: - The windows side by side

struct WindowCompareChart: View {
    let summaries: [Int: FinanceSummary]
    @Environment(\.strings) private var strings

    private struct Point: Identifiable {
        let window: String
        let series: String
        let minor: Int64
        var id: String { window + "|" + series }
    }

    private var points: [Point] {
        FinanceModel.windows.flatMap { days -> [Point] in
            guard let summary = summaries[days] else { return [] }
            let window = strings["admin.finance.period", ["days": days]]
            let perDay = Int64(days)
            return [
                Point(window: window, series: strings["admin.finance.gross"], minor: summary.grossMinor / perDay),
                Point(window: window, series: strings["admin.finance.platform"], minor: summary.platformMinor / perDay),
            ]
        }
    }

    var body: some View {
        let gross = strings["admin.finance.gross"]
        let platform = strings["admin.finance.platform"]
        ChartCard(title: strings["ops.finance.compare_title"]) {
            if points.allSatisfy({ $0.minor == 0 }) {
                EmptyChartNote()
            } else {
                Chart(points) { point in
                    BarMark(
                        x: .value(strings["admin.col.period"], point.window),
                        y: .value(strings["admin.col.amount"], ChartMoney.afghani(point.minor))
                    )
                    .foregroundStyle(by: .value(strings["admin.col.type"], point.series))
                    .position(by: .value(strings["admin.col.type"], point.series))
                    .cornerRadius(3)
                    .accessibilityLabel(point.window + " · " + point.series)
                    .accessibilityValue(OpsFormat.money(minor: point.minor, strings: strings))
                }
                .chartForegroundStyleScale(domain: [gross, platform], range: [Palette.accent.opacity(0.4), Palette.accent])
                .chartLegend(position: .bottom, alignment: .leading)
                .chartYAxis {
                    AxisMarks(position: .leading) { value in
                        AxisGridLine()
                        AxisValueLabel {
                            if let amount = value.as(Double.self) {
                                Text(ChartMoney.axis(amount, strings)).opsFont(.caption)
                            }
                        }
                    }
                }
                .chartXAxis {
                    AxisMarks { value in
                        AxisValueLabel {
                            if let label = value.as(String.self) {
                                Text(label).opsFont(.caption)
                            }
                        }
                    }
                }
                .frame(height: 220)
            }
        }
    }
}

// MARK: - The last seven days

struct WeekFaresChart: View {
    let history: WeekHistory
    @Environment(\.strings) private var strings

    private struct Bar: Identifiable {
        let day: String
        /// The whole date, for VoiceOver.
        let full: String
        let series: String
        let minor: Int64
        var id: String { day + "|" + series }
    }

    /// The day of the month alone, "۲۱" / "21": seven dates with their month
    /// names ran into each other on a phone. The card's subtitle says which
    /// week; VoiceOver reads the full date on each bar.
    private func shortDay(_ day: HistoryDay) -> String {
        guard let date = day.day else { return day.date }
        return OpsFormat.date(date, strings).split(separator: " ").first.map(String.init) ?? day.date
    }

    private func fullDay(_ day: HistoryDay) -> String {
        day.day.map { OpsFormat.date($0, strings) } ?? day.date
    }

    private var bars: [Bar] {
        let platform = strings["admin.finance.platform"]
        let driver = strings["admin.finance.driver"]
        return history.days.flatMap { day -> [Bar] in
            let label = shortDay(day)
            let full = fullDay(day)
            return [
                Bar(day: label, full: full, series: platform, minor: max(day.commissionMinor, 0)),
                Bar(day: label, full: full, series: driver, minor: max(day.revenueMinor - day.commissionMinor, 0)),
            ]
        }
    }

    var body: some View {
        let platform = strings["admin.finance.platform"]
        let driver = strings["admin.finance.driver"]
        ChartCard(
            title: strings["admin.week.fares_title", ["currency": strings["common.label.currency_afn"]]],
            subtitle: strings["admin.ops.week"]
        ) {
            if history.days.allSatisfy({ $0.revenueMinor == 0 }) {
                Text(strings["admin.week.empty"])
                    .opsFont(.body)
                    .foregroundStyle(Palette.textMuted)
                    .frame(maxWidth: .infinity, minHeight: 120)
            } else {
                Chart(bars) { bar in
                    BarMark(
                        x: .value(strings["admin.week.day"], bar.day),
                        y: .value(strings["admin.col.amount"], ChartMoney.afghani(bar.minor))
                    )
                    .foregroundStyle(by: .value(strings["admin.col.type"], bar.series))
                    .cornerRadius(2)
                    .accessibilityLabel(bar.full + OpsJoin.separator(strings) + bar.series)
                    .accessibilityValue(OpsFormat.money(minor: bar.minor, currency: history.currency, strings: strings))
                }
                .chartForegroundStyleScale(domain: [platform, driver], range: [Palette.accent, Palette.attention])
                .chartLegend(position: .bottom, alignment: .leading)
                .chartYAxis {
                    AxisMarks(position: .leading) { value in
                        AxisGridLine()
                        AxisValueLabel {
                            if let amount = value.as(Double.self) {
                                Text(ChartMoney.axis(amount, strings)).opsFont(.caption)
                            }
                        }
                    }
                }
                .chartXAxis {
                    AxisMarks { value in
                        AxisValueLabel {
                            if let label = value.as(String.self) {
                                Text(label).opsFont(.caption)
                            }
                        }
                    }
                }
                .frame(height: 220)
            }
        }
    }
}
