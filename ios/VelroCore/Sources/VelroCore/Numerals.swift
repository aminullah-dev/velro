/// Digits, formatted for the reader.
///
/// Storage is always Latin digits; this is display only. Dari and Pashto
/// readers expect Eastern Arabic-Indic digits in prose, English readers Latin.
/// The same rule as the Android app's `Numerals`, so a fare reads the same on
/// both phones.
public enum Numerals {
    private static let eastern = Array("۰۱۲۳۴۵۶۷۸۹")
    private static let arabic = Array("٠١٢٣٤٥٦٧٨٩")

    public static func localise(_ text: String, _ locale: AppLocale) -> String {
        guard locale != .english else { return text }
        return String(text.map { ch in
            if let digit = ch.wholeNumberValue, ch.isASCII { eastern[digit] } else { ch }
        })
    }

    public static func format(_ value: some BinaryInteger, _ locale: AppLocale) -> String {
        localise(String(value), locale)
    }

    /// Always Latin digits: phone numbers, codes and plates.
    ///
    /// A Persian keyboard types ۰-۹ and an Arabic one ٠-٩; both reach the
    /// server as 0-9, or the number is refused as malformed.
    public static func latin(_ text: String) -> String {
        String(text.map { ch in
            if let index = eastern.firstIndex(of: ch) ?? arabic.firstIndex(of: ch) {
                Character(String(index))
            } else {
                ch
            }
        })
    }
}

public enum MoneyFormatter {
    private static let minorDigits = ["AFN": 2, "USD": 2, "EUR": 2, "PKR": 2]

    /// "۵۰۰ افغانی" or "500 AFN", from integer minor units.
    ///
    /// No floating point touches this path, so a fare never renders as
    /// 449.99999. Grouping and the sign follow the Android formatter exactly.
    /// `showPlus` marks a gain -- "+۵۰ افغانی" beside an offer above the ask --
    /// with the sign held to its number the same way a minus is.
    public static func format(minor: Int64, currency: String, strings: Strings, showPlus: Bool = false) -> String {
        let digits = minorDigits[currency] ?? 2
        let negative = minor < 0
        let magnitude = negative ? -minor : minor
        var scale: Int64 = 1
        for _ in 0..<digits { scale *= 10 }
        let whole = magnitude / scale
        let fraction = magnitude % scale

        var plain = group(String(whole))
        if fraction != 0 {
            var tail = String(fraction)
            tail = String(repeating: "0", count: digits - tail.count) + tail
            while tail.hasSuffix("0") { tail.removeLast() }
            plain += "." + tail
        }
        let number = Numerals.localise(plain, strings.locale)
        return "\(signed(number, negative: negative, showPlus: showPlus && minor > 0)) \(strings["common.label.currency_afn"])"
    }

    /// A signed number whose sign stays beside it.
    ///
    /// Inside a right-to-left paragraph a leading minus drifts to the other
    /// end of Eastern digits. The isolate (LRI…PDI) pins sign and digits into
    /// one left-to-right run, which is how numbers are read in Dari and Pashto
    /// too. U+2212 because this is a minus, not a hyphen.
    public static func signed(_ number: String, negative: Bool, showPlus: Bool = false) -> String {
        let sign: String
        if negative {
            sign = "\u{2212}"
        } else if showPlus {
            sign = "+"
        } else {
            return number
        }
        return "\u{2066}" + sign + number + "\u{2069}"
    }

    private static func group(_ digits: String) -> String {
        var out = ""
        for (index, ch) in digits.reversed().enumerated() {
            if index > 0 && index % 3 == 0 { out.append(",") }
            out.append(ch)
        }
        return String(out.reversed())
    }
}
