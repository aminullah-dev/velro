/// Matching place names the way people type them.
///
/// Mirrors the server's `domain/text.py` and the Android `PlaceNames`. The same
/// village is written with an Arabic yeh or a Persian one, with or without a
/// zero-width non-joiner, with heh or teh marbuta -- and a passenger looking
/// for their own village should not have to guess which spelling was entered.
///
/// Pashto's own letters are left alone: ټ ډ ړ ږ ښ ګ ڼ ې ۍ distinguish real
/// words, and folding them into Persian lookalikes would merge different places.
public enum PlaceNames {
    private static let folded: [Character: Character] = [
        "ي": "ی", "ﻯ": "ی", "ﻰ": "ی",
        "ك": "ک",
        "ة": "ه",
        "أ": "ا", "إ": "ا", "آ": "ا",
        "ؤ": "و",
    ]

    /// Zero-width joiners and marks, tatweel, and the harakat rarely typed.
    private static let dropped: Set<Unicode.Scalar> = [
        "\u{200C}", "\u{200D}", "\u{200E}", "\u{200F}", "\u{0640}",
        "\u{064B}", "\u{064C}", "\u{064D}", "\u{064E}", "\u{064F}",
        "\u{0650}", "\u{0651}", "\u{0652}", "\u{0654}", "\u{0670}",
    ]

    /// The form two names are compared in. Never stored, never displayed.
    ///
    /// Walked by scalar, not by character: a Swift `Character` fuses a letter
    /// with its harakat, and they must come off one by one.
    public static func comparisonKey(_ text: String) -> String {
        var out = String.UnicodeScalarView()
        for scalar in Numerals.latin(text.lowercased()).unicodeScalars {
            if dropped.contains(scalar) || scalar.properties.isWhitespace { continue }
            if let replacement = folded[Character(scalar)]?.unicodeScalars.first {
                out.append(replacement)
            } else {
                out.append(scalar)
            }
        }
        return String(out)
    }

    public static func matches(_ name: String, _ query: String) -> Bool {
        let key = comparisonKey(query)
        return key.isEmpty || comparisonKey(name).contains(key)
    }
}
