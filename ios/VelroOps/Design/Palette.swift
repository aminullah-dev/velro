import SwiftUI
import VelroCore
#if canImport(UIKit)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

/// The admin panel's tokens (admin/src/styles.css), so the web console and
/// this one read as one product: the greens, the one amber accent, the reds
/// and the neutrals, with the panel's own dark-theme values.
///
/// Light and dark are chosen per role, never inverted. The status pairs are
/// the measured ones the phone apps use (WCAG AA for text in both themes).
enum Palette {
    // MARK: The scale, as the stylesheet names it

    static let green900 = Color(hex: 0x06301F)
    static let green800 = Color(hex: 0x0A4A30)
    static let green700 = Color(hex: 0x0E6042)
    static let green600 = Color(hex: 0x127954)
    static let green500 = Color(hex: 0x189669)
    static let green200 = Color(hex: 0x8FD9BC)
    static let green100 = Color(hex: 0xC7ECDC)
    static let green50 = Color(hex: 0xEAF7F1)
    static let amber600 = Color(hex: 0xB45309)
    static let amber500 = Color(hex: 0xD97706)
    static let amber100 = Color(hex: 0xFEF3C7)
    static let red700 = Color(hex: 0xB42318)
    static let red500 = Color(hex: 0xD92D20)
    static let red100 = Color(hex: 0xFEE4E2)

    // MARK: Roles

    /// The page: --bg.
    static let background = dynamic(light: 0xF9FAFB, dark: 0x0D1117)
    /// A card on the page: --surface.
    static let surface = dynamic(light: 0xFFFFFF, dark: 0x13181F)
    /// A table header, a hovered row, a quiet well.
    static let surfaceMuted = dynamic(light: 0xF2F4F7, dark: 0x1B222C)
    static let text = dynamic(light: 0x101828, dark: 0xE7EBF0)
    static let textMuted = dynamic(light: 0x667085, dark: 0x9AA5B1)
    /// A card's edge: --border.
    static let border = dynamic(light: 0xE4E7EC, dark: 0x232A34)
    /// Links, the brand, the selected place: --accent.
    static let accent = dynamic(light: 0x0E6042, dark: 0x8FD9BC)
    static let onAccent = dynamic(light: 0xFFFFFF, dark: 0x06301F)
    /// A number that needs somebody: the panel's .stat-value.attention.
    static let attention = dynamic(light: 0xB45309, dark: 0xFCCF7A)
    /// The start edge of a card that needs somebody: .card-link.attention.
    static let attentionEdge = amber500
    static let danger = dynamic(light: 0xB42318, dark: 0xFDA29B)
    /// The dispatcher's at-risk row: tbody tr.at-risk.
    static let atRisk = dynamic(light: 0xFEF3C7, dark: 0x2A2210)

    static let bannerError = dynamic(light: 0xFEE4E2, dark: 0x4C1512)
    static let onBannerError = dynamic(light: 0xB42318, dark: 0xFDA29B)
    static let bannerInfo = dynamic(light: 0xEAF7F1, dark: 0x0A4A30)
    static let onBannerInfo = dynamic(light: 0x0E6042, dark: 0xC7ECDC)
    static let bannerWarning = dynamic(light: 0xFEF3C7, dark: 0x4A2B06)
    static let onBannerWarning = dynamic(light: 0xB45309, dark: 0xFCCF7A)

    // MARK: Status chips (.chip.*)

    private static let chipNeutral = (dynamic(light: 0xF2F4F7, dark: 0x1B222C), dynamic(light: 0x344054, dark: 0xD0D5DD))
    private static let chipActive = (dynamic(light: 0xEAF7F1, dark: 0x0A4A30), dynamic(light: 0x0E6042, dark: 0x8FD9BC))
    private static let chipAttention = (dynamic(light: 0xFEF3C7, dark: 0x4A2B06), dynamic(light: 0xB45309, dark: 0xFCCF7A))
    private static let chipEnded = (dynamic(light: 0xF2F4F7, dark: 0x1B222C), dynamic(light: 0x667085, dark: 0x828EA0))
    private static let chipFailed = (dynamic(light: 0xFEE4E2, dark: 0x4C1512), dynamic(light: 0xB42318, dark: 0xFDA29B))

    /// A status's ground and ink. The word is always there too: colour never
    /// carries the meaning alone.
    static func chip(_ tone: StatusTone) -> (background: Color, foreground: Color) {
        switch tone {
        case .neutral: chipNeutral
        case .active: chipActive
        case .attention: chipAttention
        case .ended: chipEnded
        case .failed: chipFailed
        }
    }

    /// One colour per appearance. The one place the platforms differ: SwiftUI
    /// has no light/dark pair of its own outside an asset catalog.
    private static func dynamic(light: UInt32, dark: UInt32) -> Color {
        #if canImport(UIKit)
        Color(uiColor: UIColor { traits in
            traits.userInterfaceStyle == .dark ? UIColor(rgb: dark) : UIColor(rgb: light)
        })
        #else
        Color(nsColor: NSColor(name: nil) { appearance in
            appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? NSColor(rgb: dark) : NSColor(rgb: light)
        })
        #endif
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255,
            opacity: 1
        )
    }
}

#if canImport(UIKit)
private extension UIColor {
    convenience init(rgb: UInt32) {
        self.init(
            red: CGFloat((rgb >> 16) & 0xFF) / 255, green: CGFloat((rgb >> 8) & 0xFF) / 255,
            blue: CGFloat(rgb & 0xFF) / 255, alpha: 1
        )
    }
}
#else
private extension NSColor {
    convenience init(rgb: UInt32) {
        self.init(
            srgbRed: CGFloat((rgb >> 16) & 0xFF) / 255, green: CGFloat((rgb >> 8) & 0xFF) / 255,
            blue: CGFloat(rgb & 0xFF) / 255, alpha: 1
        )
    }
}
#endif

/// The panel's 4pt grid: --s-1 … --s-12.
enum Spacing {
    static let s1: CGFloat = 4
    static let s2: CGFloat = 8
    static let s3: CGFloat = 12
    static let s4: CGFloat = 16
    static let s5: CGFloat = 20
    static let s6: CGFloat = 24
    static let s8: CGFloat = 32
    static let s12: CGFloat = 48
}

/// --r-sm, --r-md, --r-lg.
enum Radius {
    static let sm: CGFloat = 8
    static let md: CGFloat = 12
    static let lg: CGFloat = 16
}

extension View {
    /// A card on the page: --surface, a 1pt --border, --r-lg corners.
    func opsCard(padding: CGFloat = Spacing.s4) -> some View {
        self
            .padding(padding)
            .background(Palette.surface, in: RoundedRectangle(cornerRadius: Radius.lg, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: Radius.lg, style: .continuous)
                    .strokeBorder(Palette.border, lineWidth: 1)
            }
    }
}
