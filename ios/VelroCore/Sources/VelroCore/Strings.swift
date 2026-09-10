import Foundation

/// Message keys, resolved from the same JSON files the backend and the Android
/// app use.
///
/// The files live in `backend/resources/locales` and are bundled into the app
/// as they are, not copied: a sentence corrected there is corrected here, and
/// a key the server sends cannot be missing on the phone. No user-visible
/// literal appears anywhere else in the app.
public struct Strings: Sendable {
    public let locale: AppLocale
    private let translations: [String: String]
    private let fallback: [String: String]

    public init(locale: AppLocale, translations: [String: String], fallback: [String: String]) {
        self.locale = locale
        self.translations = translations
        self.fallback = fallback
    }

    /// Reads `<tag>.json` from the bundle, with English underneath it: English
    /// is the only file guaranteed to be complete.
    public static func load(_ locale: AppLocale, bundle: Bundle = .main) -> Strings {
        let english = read(AppLocale.english.tag, bundle: bundle)
        let own = locale == .english ? english : read(locale.tag, bundle: bundle)
        return Strings(locale: locale, translations: own, fallback: english)
    }

    public static func read(_ tag: String, bundle: Bundle) -> [String: String] {
        guard
            let url = bundle.url(forResource: tag, withExtension: "json"),
            let data = try? Data(contentsOf: url),
            let map = try? JSONDecoder().decode([String: String].self, from: data)
        else { return [:] }
        return map
    }

    /// The sentence for a key. An unknown key comes back as itself: a screen
    /// showing `auth.field.phone` is an obvious bug report, a blank is not.
    public subscript(_ key: String) -> String {
        translations[key] ?? fallback[key] ?? key
    }

    /// The sentence with `{name}` placeholders filled in.
    ///
    /// Numbers are written in the reader's digits. A `<name>_minor` amount
    /// beside a `currency` becomes real money under `{name}` -- and under
    /// `{amount}` when it is the only one -- because the server sends money
    /// the way a machine should and a sentence needs it the way a person does.
    public subscript(_ key: String, _ params: [String: Any]) -> String {
        let template = self[key]
        guard !params.isEmpty else { return template }
        let resolved = withMoney(params)
        return template.replacing(/\{(\w+)\}/) { match in
            let name = String(match.output.1)
            guard let value = resolved[name] else { return String(match.output.0) }
            return format(value)
        }
    }

    public func has(_ key: String) -> Bool {
        translations[key] != nil || fallback[key] != nil
    }

    /// The sentence for a server error code. The code is the contract; an
    /// unregistered one reads as a general failure rather than as the code.
    public func forErrorCode(_ code: String, context: [String: Any] = [:]) -> String {
        let key = "error." + code.lowercased()
        return has(key) ? self[key, context] : self["error.internal_error"]
    }

    private func withMoney(_ params: [String: Any]) -> [String: Any] {
        guard let currency = params["currency"] as? String else { return params }
        let minors = params.keys.filter { $0.hasSuffix("_minor") }
        guard !minors.isEmpty else { return params }
        var out = params
        for key in minors {
            guard let minor = Self.integer(params[key]) else { continue }
            let money = MoneyFormatter.format(minor: minor, currency: currency, strings: self)
            out[String(key.dropLast("_minor".count))] = money
            if minors.count == 1, out["amount"] == nil { out["amount"] = money }
        }
        return out
    }

    private func format(_ value: Any) -> String {
        if let number = Self.integer(value) { return Numerals.format(number, locale) }
        if let number = value as? Double { return Numerals.localise(String(number), locale) }
        return String(describing: value)
    }

    private static func integer(_ value: Any?) -> Int64? {
        switch value {
        case let number as Int64: number
        case let number as Int: Int64(number)
        case let number as Int32: Int64(number)
        default: nil
        }
    }
}
