import SwiftUI

/// The brand field a signed-out screen opens with.
///
/// The sign-in form is six controls; centred on a tall screen they leave most
/// of it empty, which is what makes a careful screen look unfinished. So the
/// brand takes the top of the display, the name sits on the floor of the
/// field, and the form's card overlaps its lower edge. No photograph: a flat
/// field and a drawn texture cost nothing on a metered connection.
struct BrandHero: View {
    let title: String
    let subtitle: String
    /// A floor, not a fixed height: in Pashto at the largest text size the
    /// name and tagline are taller than any fraction of the screen.
    var minHeight: CGFloat = 0
    /// The status bar's height. The field runs up behind it, the words must
    /// not, and inside a scroll view that ignores the safe area nothing else
    /// knows where it is.
    var topInset: CGFloat = 0

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.xs) {
            Text(title)
                .velroFont(.display)
                .foregroundStyle(Palette.onBrandField)
            Text(subtitle)
                .velroFont(.heading)
                .foregroundStyle(Palette.brandSubtitle)
        }
        .frame(maxWidth: .infinity, minHeight: minHeight, alignment: .bottomLeading)
        .padding(.horizontal, Spacing.gutter)
        .padding(.top, Spacing.xxl + topInset)
        .padding(.bottom, Spacing.xxxl + Spacing.xl)
        .background(alignment: .top) {
            UnevenRoundedRectangle(bottomLeadingRadius: Radius.xl, bottomTrailingRadius: Radius.xl, style: .continuous)
                .fill(Palette.brandField)
                .overlay(alignment: .topTrailing) { HaloTexture() }
                .ignoresSafeArea(edges: .top)
        }
        .preference(key: BrandStatusBar.self, value: true)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isHeader)
    }
}

/// The dot field in the trailing top corner, fading with distance from it.
///
/// The trailing corner is the left in Dari and Pashto. A canvas draws in fixed
/// coordinates and is not mirrored like a layout is, so the direction is read
/// and x flipped by hand.
private struct HaloTexture: View {
    @Environment(\.layoutDirection) private var direction

    var body: some View {
        Canvas { context, size in
            let step: CGFloat = 14
            let radius: CGFloat = 1.6
            let count = 7
            for column in 0..<count {
                for row in 0..<count {
                    let falloff = 1 - Double(column + row) / Double(count * 2)
                    let inset = CGFloat(column + 1) * step
                    let x = direction == .rightToLeft ? inset : size.width - inset
                    let y = CGFloat(row + 1) * step
                    let dot = CGRect(x: x - radius, y: y - radius, width: radius * 2, height: radius * 2)
                    context.fill(Path(ellipseIn: dot), with: .color(Palette.brandHalo.opacity(0.30 * falloff)))
                }
            }
        }
        .frame(width: 14 * 8, height: 14 * 8)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}
