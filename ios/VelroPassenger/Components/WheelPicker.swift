import SwiftUI

/// A column of choices that turns like a drum: the chosen one large and
/// green in the middle, the rest smaller and fainter the further they are.
///
/// Every row is also a button, so a tap chooses as well as a turn -- a drum
/// alone asks for a precise flick from a thumb on a bumpy road, and a screen
/// reader can step through buttons where it cannot turn a drum.
struct WheelPicker<Value: Hashable>: View {
    struct Item {
        let value: Value
        let label: String
        var identifier = ""
    }

    let items: [Item]
    /// Nil while nothing on this drum is chosen: it rests at its top row,
    /// and turning or tapping it is what chooses.
    let selection: Value?
    let choose: (Value) -> Void
    var visibleRows = 5

    private let rowHeight: CGFloat = 46
    @State private var scrolled: Value?

    var body: some View {
        let height = rowHeight * CGFloat(visibleRows)
        ScrollView(.vertical) {
            LazyVStack(spacing: 0) {
                ForEach(items.indices, id: \.self) { index in
                    row(items[index], height: height)
                }
            }
            .scrollTargetLayout()
        }
        .scrollIndicators(.hidden)
        .scrollTargetBehavior(.viewAligned)
        .scrollPosition(id: $scrolled, anchor: .center)
        .contentMargins(.vertical, (height - rowHeight) / 2, for: .scrollContent)
        .frame(height: height)
        // Only a real choice moves the drum on appearing: one resting at "no
        // choice yet" must not choose its top row by being drawn.
        .onAppear { if let selection { scrolled = selection } }
        .onChange(of: selection) { _, new in
            if let new, new != scrolled { withAnimation(.snappy) { scrolled = new } }
        }
        .onChange(of: scrolled) { _, new in
            if let new, new != selection { choose(new) }
        }
    }

    private func row(_ item: Item, height: CGFloat) -> some View {
        let chosen = item.value == selection
        return Button {
            choose(item.value)
        } label: {
            Text(item.label)
                .velroFont(chosen ? .title : .body, weight: chosen ? .bold : .regular)
                .foregroundStyle(chosen ? Palette.primary : Palette.onSurfaceVariant)
                .lineLimit(1)
                .minimumScaleFactor(0.7)
                .frame(maxWidth: .infinity, minHeight: rowHeight)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .id(item.value)
        .accessibilityIdentifier(item.identifier)
        .accessibilityAddTraits(chosen ? .isSelected : [])
        // Smaller and fainter with distance from the middle, as a drum's
        // faces turn away from the eye.
        .visualEffect { content, proxy in
            let middle = proxy.frame(in: .scrollView(axis: .vertical)).midY
            let distance = min(abs(middle - height / 2) / (height / 2), 1)
            return content
                .scaleEffect(1 - distance * 0.28)
                .opacity(1 - distance * 0.6)
        }
    }
}

/// The band behind the middle row of a set of drums: where the choice is.
struct WheelBand: View {
    var body: some View {
        Capsule()
            .fill(Palette.primaryContainer)
            .frame(height: 46)
            .accessibilityHidden(true)
    }
}
