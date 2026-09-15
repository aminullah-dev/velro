import SwiftUI
import VelroCore

/// Money from integer minor units, in the reader's digits.
///
///     MoneyText(settlement.amount)
///     MoneyText(minor: booking.fareTotalMinor, currency: booking.fareCurrency)
struct MoneyText: View {
    @Environment(\.strings) private var strings
    private let minor: Int64
    private let currency: String
    private let showPlus: Bool

    init(_ money: Money, showPlus: Bool = false) {
        self.init(minor: money.amountMinor, currency: money.currency, showPlus: showPlus)
    }

    init(minor: Int64, currency: String = "AFN", showPlus: Bool = false) {
        self.minor = minor
        self.currency = currency
        self.showPlus = showPlus
    }

    var body: some View {
        Text(OpsFormat.money(minor: minor, currency: currency, strings: strings, showPlus: showPlus))
            .monospacedDigit()
    }
}

/// A server timestamp in Kabul time -- Hijri Shamsi and Eastern digits for
/// Dari and Pashto. Nil or unreadable is a dash. `.relative` keeps itself
/// current.
///
///     DateText(trip.scheduledDepartureAt)
///     DateText(entry.occurredAt, style: .relative)
///     DateText(document.expiresOn)             // a day: date only
struct DateText: View {
    @Environment(\.strings) private var strings
    private let date: Date?
    private let isDay: Bool
    private let style: DateStyle

    init(_ iso: String?, style: DateStyle = .dateTime) {
        if let day = ISODate.parseDay(iso) {
            date = day
            isDay = true
        } else {
            date = ISODate.parse(iso)
            isDay = false
        }
        self.style = style
    }

    init(_ date: Date?, style: DateStyle = .dateTime) {
        self.date = date
        self.isDay = false
        self.style = style
    }

    var body: some View {
        if let date {
            if style == .relative && !isDay {
                TimelineView(.periodic(from: .now, by: 30)) { context in
                    Text(OpsFormat.relative(date, now: context.date, strings))
                }
            } else {
                Text(OpsFormat.format(date, style: isDay ? .date : style, strings: strings))
                    .monospacedDigit()
            }
        } else {
            Text("—").foregroundStyle(Palette.textMuted)
        }
    }
}

/// Latin text inside right-to-left prose -- a plate, a booking number, a
/// reference -- held in one left-to-right run so the bidi algorithm cannot
/// reorder it (the panel's `.ltr`).
struct LTRText: View {
    private let value: String

    init(_ value: String) { self.value = value }

    var body: some View {
        Text("\u{2066}\(value)\u{2069}")
            .monospacedDigit()
    }
}

/// A phone number an operator can ring with one tap: Latin, unmirrored, and
/// a `tel:` link. Nil (a deleted account) is a dash.
struct PhoneLink: View {
    private let number: String?

    init(_ number: String?) { self.number = number }

    var body: some View {
        if let number, !number.isEmpty,
           let url = URL(string: "tel:" + number.filter { $0.isNumber || $0 == "+" }) {
            Link(destination: url) { LTRText(number) }
        } else {
            Text("—").foregroundStyle(Palette.textMuted)
        }
    }
}
