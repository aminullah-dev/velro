import Foundation
import VelroCore

/// How a moment is written.
enum DateStyle: Sendable {
    /// "۲۴ سنبله ۱۴۰۵، ۰۸:۳۰" / "14 Sep 2026, 08:30".
    case dateTime
    /// The day alone.
    case date
    /// Kabul time alone.
    case time
    /// "5 min ago", "3 h ago", "2 days ago".
    case relative
}

/// Numbers, money and dates for the reader: the admin panel's formatting
/// (admin/src/i18n/StringsProvider.tsx) on top of VelroCore's rules.
///
/// Eastern digits and Hijri Shamsi for Dari and Pashto, Latin digits and
/// Gregorian for English; Kabul time always, because that is where the trips
/// are. Money is integer minor units until this moment.
enum OpsFormat {
    static func count(_ value: Int, _ strings: Strings) -> String {
        let digits = String(value.magnitude)
        var grouped = ""
        for (index, character) in digits.reversed().enumerated() {
            if index > 0 && index % 3 == 0 { grouped.append(",") }
            grouped.append(character)
        }
        let number = Numerals.localise(String(grouped.reversed()), strings.locale)
        return value < 0 ? MoneyFormatter.signed(number, negative: true) : number
    }

    /// "۵۰۰ افغانی" / "500 AFN". An unknown currency prints as its code
    /// rather than being silently labelled as afghanis.
    static func money(minor: Int64, currency: String = "AFN", strings: Strings, showPlus: Bool = false) -> String {
        let afghani = MoneyFormatter.format(minor: minor, currency: currency, strings: strings, showPlus: showPlus)
        guard currency != "AFN" else { return afghani }
        let afnLabel = " " + strings["common.label.currency_afn"]
        let number = afghani.hasSuffix(afnLabel) ? String(afghani.dropLast(afnLabel.count)) : afghani
        let key = "common.label.currency_\(currency.lowercased())"
        return number + " " + (strings.has(key) ? strings[key] : currency)
    }

    static func money(_ money: Money, strings: Strings, showPlus: Bool = false) -> String {
        self.money(minor: money.amountMinor, currency: money.currency, strings: strings, showPlus: showPlus)
    }

    /// "۲۵٪" / "25%"; nil (nothing on offer) is a dash, not 0%.
    static func percent(_ value: Int?, _ strings: Strings) -> String {
        guard let value else { return "—" }
        return strings.locale == .english ? "\(value)%" : Numerals.format(value, strings.locale) + "٪"
    }

    /// "۱۲/۲۰" / "12/20": a part of a whole -- seats booked of seats, papers
    /// verified of papers. Held in one left-to-right run, or a right-to-left
    /// line would read it as twenty out of twelve.
    static func fraction(_ part: Int, of whole: Int, _ strings: Strings) -> String {
        "\u{2066}" + Numerals.format(part, strings.locale) + "/" + Numerals.format(whole, strings.locale) + "\u{2069}"
    }

    static func date(_ date: Date, _ strings: Strings) -> String { Calendars.date(date, strings.locale) }

    static func time(_ date: Date, _ strings: Strings) -> String { Calendars.time(date, strings.locale) }

    static func dateTime(_ date: Date, _ strings: Strings) -> String {
        Calendars.date(date, strings.locale) + (strings.locale.isRTL ? "، " : ", ") + Calendars.time(date, strings.locale)
    }

    /// How long ago, in the panel's words. A moment in the future is written
    /// in full instead.
    static func relative(_ date: Date, now: Date = .now, _ strings: Strings) -> String {
        let seconds = now.timeIntervalSince(date)
        guard seconds >= 0 else { return dateTime(date, strings) }
        return age(seconds: Int(seconds), strings)
    }

    /// "5 min ago" from a count of seconds -- a driver's `location_age_seconds`.
    /// Nil is "Never".
    static func age(seconds: Int?, _ strings: Strings) -> String {
        guard let seconds else { return strings["common.value.never"] }
        let minutes = max(0, seconds) / 60
        if minutes < 60 { return strings["common.value.minutes_ago", ["minutes": minutes]] }
        let hours = minutes / 60
        if hours < 48 { return strings["common.value.hours_ago", ["hours": hours]] }
        return strings["common.value.days_ago", ["days": hours / 24]]
    }

    static func format(_ date: Date, style: DateStyle, strings: Strings, now: Date = .now) -> String {
        switch style {
        case .dateTime: dateTime(date, strings)
        case .date: self.date(date, strings)
        case .time: time(date, strings)
        case .relative: relative(date, now: now, strings)
        }
    }

    /// A server timestamp or calendar day as text. A day ("2026-09-10") is
    /// only ever a date: it has no time to show.
    static func format(_ iso: String?, style: DateStyle, strings: Strings) -> String? {
        if let day = ISODate.parseDay(iso) {
            return self.date(day, strings)
        }
        return ISODate.parse(iso).map { format($0, style: style, strings: strings) }
    }
}
