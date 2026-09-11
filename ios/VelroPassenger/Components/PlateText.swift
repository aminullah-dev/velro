import SwiftUI

/// A number plate, as it reads on the metal.
struct PlateText: View {
    let plate: String

    var body: some View {
        Text(plate)
            .font(.system(.subheadline, design: .monospaced).weight(.semibold))
            .padding(.horizontal, Spacing.sm)
            .padding(.vertical, Spacing.xxs)
            .background(Palette.surfaceVariant, in: RoundedRectangle(cornerRadius: 6))
            .foregroundStyle(Palette.onSurface)
            .environment(\.layoutDirection, .leftToRight)
    }
}
