import SwiftUI

/// Chips that wrap onto a second line instead of shrinking their labels:
/// "In two days" in Pashto does not fit where "Now" does.
struct FlowLayout: Layout {
    var spacing: CGFloat = Spacing.sm

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? .infinity
        var x: CGFloat = 0, y: CGFloat = 0, row: CGFloat = 0, widest: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x > 0 && x + size.width > width {
                x = 0
                y += row + spacing
                row = 0
            }
            x += size.width + spacing
            row = max(row, size.height)
            widest = max(widest, x - spacing)
        }
        return CGSize(width: proposal.width ?? widest, height: y + row)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var x = bounds.minX, y = bounds.minY, row: CGFloat = 0
        for view in subviews {
            let size = view.sizeThatFits(.unspecified)
            if x > bounds.minX && x + size.width > bounds.maxX {
                x = bounds.minX
                y += row + spacing
                row = 0
            }
            view.place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
            x += size.width + spacing
            row = max(row, size.height)
        }
    }
}

/// Where the passenger is in a form of several steps. A number as well as a
/// bar: the bar alone says nothing to a screen reader.
struct StepProgress: View {
    let current: Int
    let total: Int
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.xs) {
            GeometryReader { geometry in
                ZStack(alignment: .leading) {
                    Capsule().fill(Palette.surfaceVariant)
                    Capsule().fill(Palette.primary)
                        .frame(width: geometry.size.width * CGFloat(current + 1) / CGFloat(total))
                }
            }
            .frame(height: 4)
            Text(strings["common.state.step", ["current": current + 1, "total": total]])
                .velroFont(.caption)
                .foregroundStyle(Palette.onSurfaceVariant)
        }
        .accessibilityElement(children: .combine)
        .animation(.easeOut(duration: 0.25), value: current)
    }
}

/// A row that goes somewhere: a card with a name and the forward chevron,
/// which points left in Dari and Pashto.
struct PlaceRow: View {
    let title: String
    var subtitle: String?
    var systemImage: String?
    var emphasised = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VelroCard {
                HStack(spacing: Spacing.md) {
                    if let systemImage {
                        Image(systemName: systemImage)
                            .foregroundStyle(Palette.primary)
                            .accessibilityHidden(true)
                    }
                    VStack(alignment: .leading, spacing: Spacing.xxs) {
                        Text(title)
                            .velroFont(.body, weight: emphasised ? .medium : .regular)
                            .foregroundStyle(Palette.onSurface)
                        if let subtitle {
                            Text(subtitle)
                                .velroFont(.caption)
                                .foregroundStyle(Palette.onSurfaceVariant)
                        }
                    }
                    Spacer(minLength: Spacing.sm)
                    Image(systemName: "chevron.forward")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(Palette.outline)
                        .accessibilityHidden(true)
                }
                .frame(minHeight: Sizing.touchTarget - Spacing.lg * 2 + 20)
            }
        }
        .buttonStyle(PressStyle())
    }
}
