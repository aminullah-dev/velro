import Charts
import SwiftUI
import VelroCore

/// The week behind today, as two small charts (admin/src/components/WeekCharts.tsx).
///
/// Today's counts answer "what is happening"; they cannot answer "is this a
/// normal Tuesday". Two charts rather than one: bookings are counted and
/// fares are afghanis, and a second y-axis on one plot would invent a
/// relationship between them that is not in the data.
struct DashWeekCharts: View {
    let history: WeekHistory
    @Environment(\.strings) private var strings

    var body: some View {
        let currencyKey = "common.label.currency_\(history.currency.lowercased())"
        let currency = strings.has(currencyKey) ? strings[currencyKey] : history.currency
        LazyVGrid(
            columns: [GridItem(.adaptive(minimum: 320), spacing: Spacing.s3, alignment: .top)],
            alignment: .leading,
            spacing: Spacing.s3
        ) {
            DashBarChart(
                title: strings["admin.week.trips_title"],
                days: history.days,
                series: [
                    DashSeries(labelKey: "admin.week.bookings", slot: 0, values: history.days.map { Double($0.bookings) }),
                    DashSeries(labelKey: "admin.week.completed", slot: 1, values: history.days.map { Double($0.completedTrips) }),
                ],
                tick: { [strings] value in OpsFormat.count(Int(value.rounded()), strings) },
                exact: { [strings] value in OpsFormat.count(Int(value.rounded()), strings) }
            )
            DashBarChart(
                title: strings["admin.week.fares_title", ["currency": currency]],
                days: history.days,
                // Drawn in afghanis, not minor units: the axis reads 12,000,
                // not 1,200,000. The exact figure goes back to minor units.
                series: [
                    DashSeries(labelKey: "admin.week.fares", slot: 0, values: history.days.map { Double($0.revenueMinor) / 100 }),
                ],
                tick: { [strings] value in OpsFormat.count(Int(value.rounded()), strings) },
                exact: { [strings, history] value in
                    OpsFormat.money(minor: Int64((value * 100).rounded()), currency: history.currency, strings: strings)
                }
            )
        }
    }
}

struct DashSeries: Identifiable {
    let labelKey: String
    /// The categorical slot: 0 blue, 1 orange.
    let slot: Int
    let values: [Double]
    var id: String { labelKey }
}

/// One series is named by the title; two get a legend. A table of the same
/// figures is a tap away, for anyone who would rather read than compare.
struct DashBarChart: View {
    let title: String
    let days: [HistoryDay]
    let series: [DashSeries]
    /// Short: axis ticks and the one direct label.
    let tick: (Double) -> String
    /// Complete: VoiceOver and the table.
    let exact: (Double) -> String

    @Environment(\.strings) private var strings
    @Environment(\.colorScheme) private var scheme
    @Environment(\.layoutDirection) private var direction
    @State private var asTable = false

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s3) {
            HStack(alignment: .firstTextBaseline, spacing: Spacing.s2) {
                Text(title)
                    .opsFont(.heading, weight: .bold)
                    .foregroundStyle(Palette.text)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                Spacer(minLength: Spacing.s2)
                Button(strings[asTable ? "admin.week.show_chart" : "admin.week.show_table"]) {
                    withAnimation(.snappy) { asTable.toggle() }
                }
                .opsFont(.caption, weight: .medium)
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
            if asTable {
                table
            } else {
                if series.count > 1 { legend }
                chart
                    .frame(height: 220)
            }
        }
        .opsCard()
    }

    // MARK: The chart

    private var isRTL: Bool { direction == .rightToLeft }

    private var maxValue: Double { series.flatMap(\.values).max() ?? 0 }

    private var ticks: [Double] { DashTicks.nice(maxValue) }

    private var chart: some View {
        let ticks = ticks
        let top = max(ticks.last ?? 1, 1)
        let dates = days.map(\.date)
        // The days run the way the reader reads: oldest on the left in
        // English, on the right in Dari and Pashto, today at the end either
        // way. The chart itself is drawn left to right, so the order is set
        // here rather than left to a mirroring nobody asked for.
        let domain = isRTL ? Array(dates.reversed()) : dates
        // The bars within a day follow the same direction: the first series
        // at the reading start.
        let ordered = isRTL ? Array(series.reversed()) : series
        let last = days.count - 1
        let labelLast = series.count == 1

        return Chart {
            ForEach(ordered) { one in
                ForEach(Array(days.enumerated()), id: \.element.date) { index, day in
                    let value = index < one.values.count ? one.values[index] : 0
                    BarMark(
                        x: .value(strings["admin.week.day"], day.date),
                        y: .value(strings[one.labelKey], value)
                    )
                    .foregroundStyle(color(one.slot))
                    .position(by: .value("series", one.labelKey))
                    .cornerRadius(3)
                    .accessibilityLabel(strings["admin.week.bar_label", [
                        "series": strings[one.labelKey], "value": exact(value), "date": fullDate(day.date),
                    ]])
                    .annotation(position: .top, spacing: 3) {
                        if labelLast && index == last && value > 0 {
                            Text(tick(value))
                                .opsFont(.caption, weight: .medium)
                                .foregroundStyle(Palette.text)
                                .monospacedDigit()
                        }
                    }
                }
            }
        }
        .chartXScale(domain: domain)
        .chartYScale(domain: 0...top)
        .chartXAxis {
            AxisMarks(values: domain) { value in
                AxisValueLabel(centered: true) {
                    if let iso = value.as(String.self) {
                        dayLabel(iso, isToday: iso == dates.last)
                    }
                }
            }
        }
        .chartYAxis {
            AxisMarks(position: isRTL ? .trailing : .leading, values: ticks) { value in
                AxisGridLine(stroke: StrokeStyle(lineWidth: value.as(Double.self) == 0 ? 1 : 0.5))
                    .foregroundStyle(value.as(Double.self) == 0 ? Palette.textMuted.opacity(0.5) : Palette.border)
                AxisValueLabel {
                    if let number = value.as(Double.self) {
                        // The system face, not opsFont: Charts sizes the tick
                        // column before the custom face applies, and a wider
                        // "6,000" was cut to "6,0…". Ticks are digits only,
                        // which the system face has in Latin and Eastern forms.
                        Text(tick(number))
                            .font(.caption)
                            .foregroundStyle(Palette.textMuted)
                            .monospacedDigit()
                            .fixedSize()
                    }
                }
            }
        }
        .chartLegend(.hidden)
        .overlay {
            if maxValue == 0 {
                Text(strings["admin.week.empty"])
                    .opsFont(.label, weight: .regular)
                    .foregroundStyle(Palette.textMuted)
                    .padding(Spacing.s2)
                    .background(Palette.surface.opacity(0.9), in: RoundedRectangle(cornerRadius: Radius.sm))
            }
        }
        .environment(\.layoutDirection, .leftToRight)
        .accessibilityLabel(title)
    }

    private var legend: some View {
        HStack(spacing: Spacing.s4) {
            ForEach(series) { one in
                HStack(spacing: Spacing.s1 + 2) {
                    RoundedRectangle(cornerRadius: 3)
                        .fill(color(one.slot))
                        .frame(width: 12, height: 12)
                        .accessibilityHidden(true)
                    Text(strings[one.labelKey])
                        .opsFont(.caption, weight: .medium)
                        .foregroundStyle(Palette.text)
                }
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func dayLabel(_ iso: String, isToday: Bool) -> some View {
        let parts = DashDays.dayMonth(iso, strings)
        return VStack(spacing: 0) {
            Text(parts.day)
                .opsFont(.caption, weight: isToday ? .bold : .regular)
            Text(parts.month)
                .opsFont(.caption, weight: isToday ? .bold : .regular)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
        }
        .foregroundStyle(isToday ? Palette.text : Palette.textMuted)
        .monospacedDigit()
    }

    // MARK: The table

    private var table: some View {
        Grid(alignment: .leading, horizontalSpacing: Spacing.s4, verticalSpacing: Spacing.s2) {
            GridRow {
                Text(strings["admin.week.day"])
                ForEach(series) { one in
                    Text(strings[one.labelKey]).gridColumnAlignment(.trailing)
                }
            }
            .opsFont(.label, weight: .medium)
            .foregroundStyle(Palette.textMuted)
            Divider()
            ForEach(Array(days.enumerated()), id: \.element.date) { index, day in
                GridRow {
                    Text(fullDate(day.date))
                    ForEach(series) { one in
                        Text(exact(index < one.values.count ? one.values[index] : 0))
                            .monospacedDigit()
                    }
                }
                .opsFont(.body)
                .foregroundStyle(Palette.text)
                .accessibilityElement(children: .combine)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Helpers

    /// Blue and orange, the panel's --viz-1 and --viz-2, lifted for dark.
    private func color(_ slot: Int) -> Color {
        let dark = scheme == .dark
        return slot == 0 ? Color(hex: dark ? 0x3987E5 : 0x2A78D6) : Color(hex: dark ? 0xD95926 : 0xEB6834)
    }

    private func fullDate(_ iso: String) -> String {
        OpsFormat.format(iso, style: .date, strings: strings) ?? iso
    }
}

/// A day's label under its bars, in the reader's calendar: "14 / Sep" in
/// English, "۲۴ / سنبله" in Dari and Pashto -- the day the driver's app calls
/// by that name. Read from the date's own parts: a calendar day is not an
/// instant, and no time zone may move it.
enum DashDays {
    static func dayMonth(_ iso: String, _ strings: Strings) -> (day: String, month: String) {
        let parts = iso.split(separator: "-").compactMap { Int($0) }
        guard parts.count == 3 else { return (iso, "") }
        let (year, month, day) = (parts[0], parts[1], parts[2])
        if strings.locale == .english {
            return (String(day), strings["common.month.\(month)"])
        }
        let shamsi = Calendars.shamsi(year: year, month: month, day: day)
        return (Numerals.format(shamsi.day, strings.locale), strings["common.shamsi_month.\(shamsi.month)"])
    }
}

/// Round steps from zero, about four of them, never below one: both charts
/// count whole things, and an axis reading 0.25 bookings is a question
/// nobody should have to ask. The web panel's `niceTicks`.
enum DashTicks {
    static func nice(_ max: Double) -> [Double] {
        guard max > 0 else { return [0] }
        let rough = max / 4
        let power = pow(10, floor(log10(rough)))
        let step = Swift.max(1, [1, 2, 5, 10].map { $0 * power }.first { $0 >= rough } ?? 10 * power)
        let highest = (max / step).rounded(.up) * step
        return Array(stride(from: 0, through: highest, by: step))
    }
}
