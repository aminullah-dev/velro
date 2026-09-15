import CoreText
import SwiftUI
import VelroCore

/// The console's type scale: the admin panel's sizes (a 24pt page title, a
/// 28pt figure, 15pt text), which suit a desk better than the phone apps'.
enum TextRole {
    case display, headline, title, heading, body, label, caption

    var size: CGFloat {
        switch self {
        case .display: 28
        case .headline: 24
        case .title: 20
        case .heading: 17
        case .body: 15
        case .label: 13
        case .caption: 12
        }
    }

    var weight: OpsFonts.Weight {
        switch self {
        case .display, .headline: .bold
        case .title, .heading, .label: .medium
        case .body, .caption: .regular
        }
    }

    /// What the size scales with when somebody turns the text size up.
    var textStyle: Font.TextStyle {
        switch self {
        case .display: .largeTitle
        case .headline: .title
        case .title: .title2
        case .heading: .headline
        case .body: .body
        case .label: .subheadline
        case .caption: .caption
        }
    }
}

/// Vazirmatn for Dari and Pashto, the system face for English.
///
/// The phone apps' own files (bundled from the Android app), verified to
/// carry all nine Pashto letters -- ټ ډ ړ ږ ښ ګ ڼ ې ۍ -- at every weight, on
/// iOS and macOS alike. Opened from their URLs, not registered by name: all
/// three carry the PostScript name "Vazirmatn-Regular", so registration would
/// keep one and draw every bold heading in the regular weight.
@MainActor
enum OpsFonts {
    enum Weight: String { case regular, medium, bold }

    private static var descriptors: [Weight: CTFontDescriptor] = [:]

    static func font(_ weight: Weight, size: CGFloat) -> Font? {
        guard let descriptor = descriptor(weight) else { return nil }
        return Font(CTFontCreateWithFontDescriptor(descriptor, size, nil))
    }

    private static func descriptor(_ weight: Weight) -> CTFontDescriptor? {
        if let cached = descriptors[weight] { return cached }
        guard
            let url = Bundle.main.url(forResource: "vazirmatn_\(weight.rawValue)", withExtension: "ttf"),
            let found = (CTFontManagerCreateFontDescriptorsFromURL(url as CFURL) as? [CTFontDescriptor])?.first
        else { return nil }
        descriptors[weight] = found
        return found
    }
}

private struct OpsTextStyle: ViewModifier {
    let role: TextRole
    let weight: OpsFonts.Weight
    @Environment(\.strings) private var strings
    @ScaledMetric private var size: CGFloat

    init(_ role: TextRole, weight: OpsFonts.Weight?) {
        self.role = role
        self.weight = weight ?? role.weight
        _size = ScaledMetric(wrappedValue: role.size, relativeTo: role.textStyle)
    }

    func body(content: Content) -> some View {
        content
            .font(font)
            // Perso-Arabic needs more leading than Latin at the same size
            // (--line-arabic 1.6 against --line-latin 1.35).
            .lineSpacing(strings.locale == .english ? size * 0.12 : size * 0.3)
    }

    private var font: Font {
        if strings.locale != .english, let vazirmatn = OpsFonts.font(weight, size: size) {
            return vazirmatn
        }
        let system: Font.Weight = switch weight {
        case .regular: .regular
        case .medium: .semibold
        case .bold: .bold
        }
        return .system(size: size, weight: system)
    }
}

extension View {
    /// A role from the scale, optionally at another of the three shipped
    /// weights. Never `.fontWeight` on top: Vazirmatn is opened from its file,
    /// and a synthesised bold smears the joins between letters.
    func opsFont(_ role: TextRole, weight: OpsFonts.Weight? = nil) -> some View {
        modifier(OpsTextStyle(role, weight: weight))
    }
}
