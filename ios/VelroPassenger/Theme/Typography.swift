import CoreText
import SwiftUI
import VelroCore

/// The type scale, as the Android theme sets it.
enum TextRole {
    case display, headline, title, heading, body, label, caption

    var size: CGFloat {
        switch self {
        case .display: 32
        case .headline: 28
        case .title: 22
        case .heading: 18
        case .body: 16
        case .label: 14
        case .caption: 12
        }
    }

    var weight: VelroFonts.Weight {
        switch self {
        case .display, .headline: .bold
        case .title, .heading, .label: .medium
        case .body, .caption: .regular
        }
    }

    /// What the size scales with when somebody turns up the system text size.
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
/// Bundled rather than left to iOS so the product reads the same on both
/// platforms, and because it is verified to carry all nine Pashto letters --
/// ټ ډ ړ ږ ښ ګ ڼ ې ۍ -- at every weight. The files are the Android app's own.
///
/// They are opened from their URLs, not registered by name: all three carry
/// the PostScript name "Vazirmatn-Regular", so registration would keep one and
/// silently draw every bold heading in the regular weight. Real weights,
/// never synthesised -- a faked bold smears the joins between letters.
@MainActor
enum VelroFonts {
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

private struct VelroTextStyle: ViewModifier {
    let role: TextRole
    let weight: VelroFonts.Weight
    @Environment(\.strings) private var strings
    @ScaledMetric private var size: CGFloat

    init(_ role: TextRole, weight: VelroFonts.Weight?) {
        self.role = role
        self.weight = weight ?? role.weight
        _size = ScaledMetric(wrappedValue: role.size, relativeTo: role.textStyle)
    }

    func body(content: Content) -> some View {
        content
            .font(font)
            // Perso-Arabic needs more leading than Latin at the same size, or
            // the descenders of one line meet the dots of the next.
            .lineSpacing(strings.locale == .english ? size * 0.12 : size * 0.3)
    }

    private var font: Font {
        if strings.locale != .english, let vazirmatn = VelroFonts.font(weight, size: size) {
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
    /// weights. Never `.fontWeight` on top: Vazirmatn is opened from its
    /// file, and iOS would silently ignore the request rather than draw it.
    func velroFont(_ role: TextRole, weight: VelroFonts.Weight? = nil) -> some View {
        modifier(VelroTextStyle(role, weight: weight))
    }
}
