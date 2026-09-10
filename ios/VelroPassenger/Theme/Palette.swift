import SwiftUI
import UIKit

/// The Android app's design tokens (`core/ui/theme/Tokens.kt`), one for one.
///
/// Every pair used for text was measured against WCAG AA there, because this is
/// read in daylight through a windscreen; the same values keep the same
/// contrast here. Light and dark are chosen per role, never inverted.
enum Palette {
    // Ground and surfaces: a card lies on a page a shade darker than itself.
    static let background = dynamic(light: 0xF9FAFB, dark: 0x0B0F14)
    static let surface = dynamic(light: 0xFFFFFF, dark: 0x13181F)
    static let surfaceVariant = dynamic(light: 0xF2F4F7, dark: 0x1B222C)
    static let onSurface = dynamic(light: 0x101828, dark: 0xE7EBF0)
    static let onSurfaceVariant = dynamic(light: 0x344054, dark: 0xD0D5DD)

    static let primary = dynamic(light: 0x0E6042, dark: 0x8FD9BC)
    static let onPrimary = dynamic(light: 0xFFFFFF, dark: 0x06301F)

    /// The edge of a control: 3.59:1 against white, so a field is findable
    /// on a cracked screen in sunlight.
    static let outline = dynamic(light: 0x7D8899, dark: 0x667085)
    /// A decorative divider, which owes no contrast.
    static let outlineVariant = dynamic(light: 0xE4E7EC, dark: 0x1B222C)

    static let primaryContainer = dynamic(light: 0xEAF7F1, dark: 0x0A4A30)
    static let onPrimaryContainer = dynamic(light: 0x06301F, dark: 0xC7ECDC)

    /// The one accent: a fare, a seat running out, the far end of a journey.
    /// Amber500 after dark, because Amber600 is 3.55:1 on the dark card.
    static let accent = dynamic(light: 0xB45309, dark: 0xD97706)

    static let error = dynamic(light: 0xB42318, dark: 0xFDA29B)

    // Status pills, one measured pair per tone per theme.
    static let toneNeutral = dynamic(light: 0xF2F4F7, dark: 0x1B222C)
    static let onToneNeutral = dynamic(light: 0x344054, dark: 0xD0D5DD)
    static let onToneEnded = dynamic(light: 0x667085, dark: 0x828EA0)
    static let toneActive = dynamic(light: 0xEAF7F1, dark: 0x0A4A30)
    static let onToneActive = dynamic(light: 0x0E6042, dark: 0x8FD9BC)
    static let toneAttention = dynamic(light: 0xFEF3C7, dark: 0x4A2B06)
    static let onToneAttention = dynamic(light: 0xB45309, dark: 0xFCCF7A)
    static let toneFailed = dynamic(light: 0xFEE4E2, dark: 0x4C1512)
    static let onToneFailed = dynamic(light: 0xB42318, dark: 0xFDA29B)

    /// A selected choice chip. Amber, as on Android: the product's one accent.
    static let chipSelected = dynamic(light: 0xFEF3C7, dark: 0x4A2B06)
    static let onChipSelected = dynamic(light: 0x101828, dark: 0xFCCF7A)

    /// The label of a control that is there but cannot be used yet: 4.70:1
    /// light and 4.82:1 dark, quieter than a live one and never absent.
    static let disabledLabel = dynamic(light: 0x5B6675, dark: 0x828EA0)

    /// The brand field and what sits on it. Constant across themes: identity,
    /// like a signboard, is the same green at noon and at night.
    static let brandField = Color(hex: 0x0E6042)
    static let onBrandField = Color.white
    static let brandSubtitle = Color(hex: 0xC7ECDC)
    static let brandHalo = Color(hex: 0x8FD9BC)

    private static func dynamic(light: UInt32, dark: UInt32) -> Color {
        Color(UIColor { traits in
            UIColor(hex: traits.userInterfaceStyle == .dark ? dark : light)
        })
    }
}

extension Color {
    init(hex: UInt32) { self.init(uiColor: UIColor(hex: hex)) }
}

extension UIColor {
    convenience init(hex: UInt32) {
        self.init(
            red: CGFloat((hex >> 16) & 0xFF) / 255,
            green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255,
            alpha: 1
        )
    }
}

/// A 4pt grid, with one half-step for a label and the value under it.
enum Spacing {
    static let xxs: CGFloat = 2
    static let xs: CGFloat = 4
    static let sm: CGFloat = 8
    static let md: CGFloat = 12
    static let lg: CGFloat = 16
    static let xl: CGFloat = 24
    static let xxl: CGFloat = 32
    static let xxxl: CGFloat = 48
    /// Wide enough that Perso-Arabic descenders never clip.
    static let gutter: CGFloat = 20
}

enum Radius {
    static let md: CGFloat = 12
    static let lg: CGFloat = 16
    static let xl: CGFloat = 24
    /// Cards: softer than a control, so a surface and a button read as
    /// different kinds of thing without either being labelled.
    static let card: CGFloat = 20
}

enum Sizing {
    /// 52pt, not 44: used one-handed in a moving vehicle, often in gloves.
    static let touchTarget: CGFloat = 52
    static let buttonHeight: CGFloat = 56
    static let fieldHeight: CGFloat = 56
}
