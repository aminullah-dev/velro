/// The three languages VELRO speaks.
///
/// The raw values are the tags the server and the locale files use, so a value
/// read from either maps straight onto a case.
public enum AppLocale: String, CaseIterable, Sendable {
    case dari = "fa-AF"
    case pashto = "ps"
    case english = "en"

    public var tag: String { rawValue }

    /// Dari and Pashto read right to left. Driven by the chosen language, not
    /// by the phone's setting: a Dari speaker on an English iPhone still gets
    /// a right-to-left app.
    public var isRTL: Bool { self != .english }

    /// An unknown tag falls back to Dari, the language most passengers read.
    public init(tag: String) {
        self = AppLocale(rawValue: tag) ?? .dari
    }

    /// Each language named in itself. The picker is how somebody who cannot
    /// read the current language finds their own, so it cannot be translated.
    public var endonym: String {
        switch self {
        case .dari: "دری"
        case .pashto: "پښتو"
        case .english: "English"
        }
    }
}
