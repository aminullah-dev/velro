import SwiftUI

/// The brand surface home opens with: the name, the controls, and the one
/// action the screen is for, on the green, running up behind the status bar.
///
/// Everything inside owes its contrast to the green rather than to white,
/// which is why the action is a white button (`OnBrandButton`) rather than
/// the page's green one.
struct BrandHeader<Actions: View, Content: View>: View {
    let title: String
    var topInset: CGFloat = 0
    @ViewBuilder var actions: Actions
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: Spacing.sm) {
                Text(title)
                    .velroFont(.title, weight: .bold)
                    .lineLimit(1)
                    .accessibilityAddTraits(.isHeader)
                Spacer(minLength: Spacing.sm)
                actions
            }
            content
        }
        .foregroundStyle(Palette.onBrandField)
        .padding(.horizontal, Spacing.gutter)
        .padding(.top, Spacing.sm + topInset)
        .padding(.bottom, Spacing.xl)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            UnevenRoundedRectangle(bottomLeadingRadius: Radius.xl, bottomTrailingRadius: Radius.xl, style: .continuous)
                .fill(Palette.brandField)
                .ignoresSafeArea(edges: .top)
        )
        .preference(key: BrandStatusBar.self, value: true)
    }
}

/// The primary action on the green: the same button as `PrimaryButton`,
/// inverted. A green button on a green field is a rectangle nobody can find.
struct OnBrandButton: View {
    let label: String
    var systemImage: String?
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Label {
                Text(label).velroFont(.label)
            } icon: {
                if let systemImage { Image(systemName: systemImage) }
            }
            .frame(maxWidth: .infinity, minHeight: Sizing.buttonHeight)
            .foregroundStyle(Palette.brandField)
            .background(Palette.onBrandField, in: RoundedRectangle(cornerRadius: Radius.lg, style: .continuous))
            .contentShape(Rectangle())
        }
        .buttonStyle(PressStyle())
    }
}
