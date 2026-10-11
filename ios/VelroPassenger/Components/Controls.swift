import SwiftUI
import VelroCore

/// A surface lying on the page: the page is a shade darker, the edge a
/// hairline that survives both sunlight and dark mode.
struct VelroCard<Content: View>: View {
    @ViewBuilder let content: Content

    var body: some View {
        content
            .padding(Spacing.lg)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Palette.surface, in: RoundedRectangle(cornerRadius: Radius.card, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: Radius.card, style: .continuous)
                    .strokeBorder(Palette.outlineVariant, lineWidth: 1)
            )
            .elevation(.low)
    }
}

/// One of a few answers, tapped rather than typed.
struct ChoiceChip: View {
    let label: String
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: Spacing.xs) {
                if selected {
                    Image(systemName: "checkmark").font(.footnote.weight(.semibold))
                }
                Text(label).velroFont(.label)
            }
            .padding(.horizontal, Spacing.md)
            .frame(minHeight: 40)
            .foregroundStyle(selected ? Palette.onChipSelected : Palette.onSurfaceVariant)
            .background(selected ? Palette.chipSelected : Color.clear, in: Capsule())
            .overlay(Capsule().strokeBorder(selected ? Color.clear : Palette.outline, lineWidth: 1))
            .frame(minHeight: Sizing.touchTarget)
            .contentShape(Rectangle())
        }
        .buttonStyle(PressStyle())
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

/// A labelled field with a visible label above it, never a placeholder alone.
///
/// Numbers -- a phone, a code -- are laid out left to right and typed in Latin
/// digits even on a right-to-left screen: they are sequences to dial, not prose.
struct VelroField: View {
    let label: String
    @Binding var text: String
    var placeholder = ""
    var keyboard: UIKeyboardType = .default
    var contentType: UITextContentType?
    var large = false
    /// A glyph at the start of the field, saying what kind of thing goes in
    /// before a word of the label is read.
    var systemImage: String?
    var identifier = ""

    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.xs) {
            Text(label)
                .velroFont(.label)
                .foregroundStyle(Palette.onSurfaceVariant)
            HStack(spacing: Spacing.md) {
                if let systemImage {
                    Image(systemName: systemImage)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(focused ? Palette.primary : Palette.outline)
                        .accessibilityHidden(true)
                }
                TextField(placeholder, text: Binding(get: { text }, set: { text = Numerals.latin($0) }))
                    .keyboardType(keyboard)
                    .textContentType(contentType)
                    .autocorrectionDisabled()
                    .textInputAutocapitalization(.never)
                    .font(large ? .system(size: 24, weight: .semibold, design: .rounded) : .system(size: 18, weight: .regular))
                    .multilineTextAlignment(large ? .center : .leading)
                    .focused($focused)
                    .accessibilityLabel(label)
                    .accessibilityIdentifier(identifier)
            }
            .padding(.horizontal, Spacing.xl - Spacing.xs)
            .frame(minHeight: Sizing.fieldHeight)
            // A pill, like the buttons: one family of shapes for everything
            // a finger is meant to land on.
            .background(Palette.surface, in: Capsule())
            .overlay(
                Capsule().strokeBorder(focused ? Palette.primary : Palette.outline, lineWidth: focused ? 2 : 1)
            )
            .elevation(.low)
            .environment(\.layoutDirection, .leftToRight)
            .contentShape(Capsule())
            .onTapGesture { focused = true }
        }
    }
}

/// A server failure, said in the language being read.
struct InlineError: View {
    let error: APIError
    @Environment(\.strings) private var strings

    var body: some View {
        Label {
            Text(strings.forErrorCode(error.code, context: error.context.arguments))
                .velroFont(.label)
        } icon: {
            Image(systemName: "exclamationmark.circle.fill")
        }
        .foregroundStyle(Palette.error)
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.vertical, Spacing.sm)
        .accessibilityElement(children: .combine)
    }
}
