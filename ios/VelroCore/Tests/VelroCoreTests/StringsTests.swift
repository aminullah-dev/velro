import Foundation
import Testing
@testable import VelroCore

/// The repository root, found from this file so the tests read the real
/// locale files and the real app sources rather than copies of them.
let iosRoot = URL(fileURLWithPath: #filePath)
    .deletingLastPathComponent()  // VelroCoreTests
    .deletingLastPathComponent()  // Tests
    .deletingLastPathComponent()  // VelroCore
    .deletingLastPathComponent()  // ios

func localeFile(_ locale: AppLocale) -> [String: String] {
    let url = iosRoot.deletingLastPathComponent()
        .appending(path: "backend/resources/locales/\(locale.tag).json")
    guard let data = try? Data(contentsOf: url),
          let map = try? JSONDecoder().decode([String: String].self, from: data)
    else { return [:] }
    return map
}

func realStrings(_ locale: AppLocale) -> Strings {
    Strings(locale: locale, translations: localeFile(locale), fallback: localeFile(.english))
}

@Suite struct StringsTests {
    @Test func placeholdersTakeTheReadersDigits() {
        #expect(realStrings(.dari)["auth.action.resend_code_in", ["seconds": 45]] == "ارسال دوباره پس از ۴۵ ثانیه")
        #expect(realStrings(.english)["auth.action.resend_code_in", ["seconds": 45]] == "Send again in 45s")
    }

    @Test func anUnknownKeyIsVisibleNotBlank() {
        #expect(realStrings(.dari)["no.such.key"] == "no.such.key")
    }

    @Test func aMissingTranslationFallsBackToEnglish() {
        let strings = Strings(locale: .pashto, translations: [:], fallback: ["a.b": "English"])
        #expect(strings["a.b"] == "English")
    }

    @Test func serverErrorCodesBecomeSentences() {
        let dari = realStrings(.dari)
        let context: [String: JSONValue] = ["attempts_remaining": .int(2)]
        #expect(dari.forErrorCode("OTP_INVALID", context: context.arguments) == "کود درست نیست. ۲ کوشش باقی مانده است.")
        // An unregistered code never reaches a passenger as a code.
        #expect(dari.forErrorCode("SOMETHING_NEW") == dari["error.internal_error"])
    }

    @Test func minorUnitsBecomeMoney() {
        let strings = Strings(
            locale: .dari,
            translations: ["k": "کمترین {amount}", "common.label.currency_afn": "افغانی"],
            fallback: [:]
        )
        #expect(strings["k", ["minimum_minor": Int64(500_000), "currency": "AFN"]] == "کمترین ۵,۰۰۰ افغانی")
    }

    @Test func aGainKeepsItsPlusBesideIt() {
        let strings = Strings(locale: .dari, translations: ["common.label.currency_afn": "افغانی"], fallback: [:])
        #expect(MoneyFormatter.format(minor: 5_000, currency: "AFN", strings: strings, showPlus: true) == "\u{2066}+۵۰\u{2069} افغانی")
        #expect(MoneyFormatter.format(minor: 5_000, currency: "AFN", strings: strings) == "۵۰ افغانی")
    }

    @Test func aNegativeAmountKeepsItsSignBesideIt() {
        let strings = Strings(locale: .english, translations: ["common.label.currency_afn": "AFN"], fallback: [:])
        #expect(MoneyFormatter.format(minor: -5_550, currency: "AFN", strings: strings) == "\u{2066}\u{2212}55.5\u{2069} AFN")
    }
}

@Suite struct NumeralsTests {
    @Test func whatIsTypedReachesTheServerInLatinDigits() {
        #expect(Numerals.latin("۰۷۰۰۱۲۳۴۵۶") == "0700123456")
        #expect(Numerals.latin("٠٧٠٠١٢٣٤٥٦") == "0700123456")
        #expect(Numerals.latin("+93 700") == "+93 700")
    }

    @Test func proseTakesEasternDigitsExceptInEnglish() {
        #expect(Numerals.format(2026, .pashto) == "۲۰۲۶")
        #expect(Numerals.format(2026, .english) == "2026")
    }
}

/// Every key the app asks for exists, in every language.
///
/// Read out of the app's own sources, so a key added to a screen and forgotten
/// in a locale file fails here rather than showing up on a phone as
/// `booking.label.seat`. The same guard the Android app has.
@Suite struct LocaleCoverageTests {
    @Test func everyKeyTheAppUsesIsTranslated() throws {
        let keys = try usedKeys()
        #expect(!keys.isEmpty)
        for locale in AppLocale.allCases {
            let file = localeFile(locale)
            let missing = keys.filter { (file[$0] ?? "").isEmpty }.sorted()
            #expect(missing.isEmpty, "\(locale.tag) lacks \(missing)")
        }
    }

    /// The system's own location prompt says what the app says, in each
    /// language -- it is a copy, so this is what stops it drifting.
    @Test func theLocationPromptMatchesTheLocaleFiles() throws {
        for (locale, lproj) in [(AppLocale.english, "en"), (.dari, "fa"), (.pashto, "ps")] {
            let url = iosRoot.appending(path: "VelroPassenger/Resources/\(lproj).lproj/InfoPlist.strings")
            let text = try String(contentsOf: url, encoding: .utf8)
            let expected = localeFile(locale)["location.permission.rationale"] ?? "missing"
            #expect(text.contains("\"NSLocationWhenInUseUsageDescription\" = \"\(expected)\";"), "\(lproj)")
        }
    }

    /// The driver app's two prompts -- location on a trip, the camera for his
    /// papers -- are copies too.
    @Test func theDriversPromptsMatchTheLocaleFiles() throws {
        for (locale, lproj) in [(AppLocale.english, "en"), (.dari, "fa"), (.pashto, "ps")] {
            let url = iosRoot.appending(path: "VelroDriver/Resources/\(lproj).lproj/InfoPlist.strings")
            let text = try String(contentsOf: url, encoding: .utf8)
            let file = localeFile(locale)
            for (plistKey, localeKey) in [("NSLocationWhenInUseUsageDescription", "location.permission.rationale.driver"),
                                          ("NSCameraUsageDescription", "camera.permission.rationale.driver")] {
                let expected = file[localeKey] ?? "missing"
                #expect(text.contains("\"\(plistKey)\" = \"\(expected)\";"), "\(lproj) \(plistKey)")
            }
        }
    }

    private func usedKeys() throws -> Set<String> {
        var keys: Set<String> = []
        for app in ["VelroPassenger", "VelroDriver"] { keys.formUnion(try usedKeys(in: app)) }
        return keys
    }

    private func usedKeys(in app: String) throws -> Set<String> {
        let sources = iosRoot.appending(path: app)
        let walker = FileManager.default.enumerator(at: sources, includingPropertiesForKeys: nil)
        // Every dotted literal in a namespace the locale files use -- not only
        // the ones written inside `strings[...]`, because keys also live in
        // tuples and `titleKey` switches. Test identifiers are taken out first.
        let namespaces = Set(localeFile(.english).keys.compactMap { $0.split(separator: ".").first.map(String.init) })
        var keys: Set<String> = ["error.network_offline", "error.internal_error"]
        while let url = walker?.nextObject() as? URL {
            guard url.pathExtension == "swift" else { continue }
            let text = try String(contentsOf: url, encoding: .utf8)
                .replacing(/(?:accessibilityIdentifier\(|identifier: )"[^"]*"/, with: "")
            for match in text.matches(of: /"([a-z0-9_]+(?:\.[a-z0-9_]+)+)"/) {
                let key = String(match.output.1)
                if let first = key.split(separator: ".").first, namespaces.contains(String(first)) {
                    keys.insert(key)
                }
            }
        }
        return keys
    }
}
