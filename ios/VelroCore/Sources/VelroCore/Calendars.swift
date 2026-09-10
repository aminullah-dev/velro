import Foundation

/// Dates and times for the reader.
///
/// Storage is UTC and Gregorian, always. Hijri Shamsi is a display format:
/// never stored, never sorted by. The conversion is the Android app's
/// `Calendars`, line for line, and is checked against the same table
/// (`docs/domain/calendar.json`) so the two phones and the operator's panel
/// cannot disagree about what day it is.
public enum Calendars {
    /// Afghanistan keeps no daylight saving; the offset is +04:30. Every time
    /// on screen is Kabul time, because "six tomorrow" means six in Ghorband
    /// even to the person testing this from Canada.
    public static let kabul = TimeZone(identifier: "Asia/Kabul")!

    public struct ShamsiDate: Equatable, Sendable {
        public let year: Int
        public let month: Int
        public let day: Int
        public init(year: Int, month: Int, day: Int) {
            self.year = year
            self.month = month
            self.day = day
        }
    }

    // 1 Hamal 1399 fell on 20 March 2020. Every conversion counts from here.
    private static let anchorYear = 1399
    private static let anchorEpochDay = epochDay(year: 2020, month: 3, day: 20)

    private static let monthsDari = [
        "حمل", "ثور", "جوزا", "سرطان", "اسد", "سنبله",
        "میزان", "عقرب", "قوس", "جدی", "دلو", "حوت",
    ]
    private static let monthsPashto = [
        "وری", "غویی", "غبرګولی", "چنګاښ", "زمری", "وږی",
        "تله", "لړم", "لیندۍ", "مرغومی", "سلواغه", "کب",
    ]
    private static let monthsEnglish = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]

    public static func time(_ date: Date, _ locale: AppLocale) -> String {
        let parts = components(date)
        return Numerals.localise(String(format: "%02d:%02d", parts.hour ?? 0, parts.minute ?? 0), locale)
    }

    /// "12 Sep 2026" in English; "۲۱ سنبله ۱۴۰۵" in Dari and Pashto.
    public static func date(_ date: Date, _ locale: AppLocale) -> String {
        let parts = components(date)
        let (year, month, day) = (parts.year ?? 1970, parts.month ?? 1, parts.day ?? 1)
        switch locale {
        case .english:
            return "\(day) \(monthsEnglish[month - 1]) \(year)"
        case .dari, .pashto:
            let shamsi = shamsi(year: year, month: month, day: day)
            let names = locale == .pashto ? monthsPashto : monthsDari
            return Numerals.localise("\(shamsi.day) \(names[shamsi.month - 1]) \(shamsi.year)", locale)
        }
    }

    public static func dateTime(_ date: Date, _ locale: AppLocale) -> String {
        "\(Calendars.date(date, locale)) \(time(date, locale))"
    }

    /// Whole minutes from now until then, never negative.
    public static func minutesUntil(_ date: Date, now: Date = .now) -> Int {
        max(0, Int(date.timeIntervalSince(now) / 60))
    }

    /// The hour it is in Kabul now.
    public static func kabulHour(_ now: Date = .now) -> Int {
        components(now).hour ?? 0
    }

    /// Midnight in Kabul, `days` from today, at `hour` o'clock.
    ///
    /// Built in Kabul's zone rather than the phone's, and not by adding
    /// seconds by hand: a half-hour offset is exactly the sort of thing that
    /// silently becomes an hour wrong when done by hand.
    public static func kabul(daysFromToday days: Int, hour: Int, now: Date = .now) -> Date {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = kabul
        let today = calendar.startOfDay(for: now)
        let day = calendar.date(byAdding: .day, value: days, to: today) ?? today
        return calendar.date(bySettingHour: hour, minute: 0, second: 0, of: day) ?? day
    }

    public static func shamsi(_ date: Date) -> ShamsiDate {
        let parts = components(date)
        return shamsi(year: parts.year ?? 1970, month: parts.month ?? 1, day: parts.day ?? 1)
    }

    /// Gregorian to Hijri Shamsi, stepped year by year from a known Nowruz
    /// rather than guessed from the equinox.
    public static func shamsi(year: Int, month: Int, day: Int) -> ShamsiDate {
        var shamsiYear = anchorYear
        var remaining = epochDay(year: year, month: month, day: day) - anchorEpochDay
        if remaining >= 0 {
            while remaining >= yearLength(shamsiYear) {
                remaining -= yearLength(shamsiYear)
                shamsiYear += 1
            }
        } else {
            while remaining < 0 {
                shamsiYear -= 1
                remaining += yearLength(shamsiYear)
            }
        }
        var monthIndex = 1
        while monthIndex <= 12 {
            let length = monthLength(shamsiYear, monthIndex)
            if remaining < length { return ShamsiDate(year: shamsiYear, month: monthIndex, day: remaining + 1) }
            remaining -= length
            monthIndex += 1
        }
        return ShamsiDate(year: shamsiYear + 1, month: 1, day: remaining + 1)
    }

    /// The 33-year cycle, as observed. The 2820-year (Birashk) rule is wrong
    /// for 1403/1404 and moved a year of dates by a day on Android once.
    public static func isLeap(_ year: Int) -> Bool {
        let residue = ((year % 33) + 33) % 33
        return [1, 5, 9, 13, 17, 22, 26, 30].contains(residue)
    }

    public static func yearLength(_ year: Int) -> Int { isLeap(year) ? 366 : 365 }

    /// Six months of 31 days, five of 30, and Hoot of 29 or 30.
    public static func monthLength(_ year: Int, _ month: Int) -> Int {
        if month <= 6 { return 31 }
        if month <= 11 { return 30 }
        return isLeap(year) ? 30 : 29
    }

    private static func components(_ date: Date) -> DateComponents {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = kabul
        return calendar.dateComponents([.year, .month, .day, .hour, .minute], from: date)
    }

    /// Days since 1970-01-01 in the proleptic Gregorian calendar.
    static func epochDay(year: Int, month: Int, day: Int) -> Int {
        let y = month <= 2 ? year - 1 : year
        let era = (y >= 0 ? y : y - 399) / 400
        let yearOfEra = y - era * 400
        let monthIndex = (month + 9) % 12
        let dayOfYear = (153 * monthIndex + 2) / 5 + day - 1
        let dayOfEra = yearOfEra * 365 + yearOfEra / 4 - yearOfEra / 100 + dayOfYear
        return era * 146_097 + dayOfEra - 719_468
    }
}

/// The server's timestamps.
///
/// Python writes `2026-09-10T11:05:00.123456+00:00`; this also accepts `Z`,
/// no fraction, and no zone at all (read as UTC). A timestamp that cannot be
/// read is nil rather than a failed screen.
public enum ISODate {
    public static func parse(_ text: String?) -> Date? {
        guard let text, !text.isEmpty else { return nil }
        guard let match = text.firstMatch(of: /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(\.\d+)?(.*)$/) else {
            return nil
        }
        let zone = match.output.3.isEmpty ? "Z" : String(match.output.3)
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        guard let whole = formatter.date(from: String(match.output.1) + zone) else { return nil }
        let fraction = match.output.2.flatMap { Double("0" + $0) } ?? 0
        return whole.addingTimeInterval(fraction)
    }

    public static func format(_ date: Date) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.string(from: date)
    }
}
