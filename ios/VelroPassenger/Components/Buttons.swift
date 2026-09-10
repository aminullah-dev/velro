import SwiftUI

/// The one action a screen exists for.
///
/// A button mid-request is disabled, not merely spinning: a double tap on a
/// slow connection is the commonest way to send a request twice. Disabled
/// still shows -- quieter, never gone -- so a person can tell an unfinished
/// form from a broken app.
struct PrimaryButton: View {
    let label: String
    var enabled = true
    var loading = false
    var pill = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            ZStack {
                if loading {
                    ProgressView().tint(Palette.onPrimary)
                } else {
                    Text(label).velroFont(.label)
                }
            }
            .frame(maxWidth: .infinity, minHeight: Sizing.buttonHeight)
            .foregroundStyle(isLive ? Palette.onPrimary : Palette.disabledLabel)
            .background(isLive ? Palette.primary : Palette.surfaceVariant, in: shape)
            .contentShape(shape)
        }
        .buttonStyle(PressStyle())
        .disabled(!isLive)
    }

    private var isLive: Bool { enabled && !loading }
    private var shape: RoundedRectangle {
        RoundedRectangle(cornerRadius: pill ? Sizing.buttonHeight / 2 : Radius.lg, style: .continuous)
    }
}

/// A second choice beside the primary one: outlined, same height.
struct SecondaryButton: View {
    let label: String
    var enabled = true
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(label)
                .velroFont(.label)
                .frame(maxWidth: .infinity, minHeight: Sizing.buttonHeight)
                .foregroundStyle(enabled ? Palette.primary : Palette.disabledLabel)
                .overlay(
                    RoundedRectangle(cornerRadius: Radius.lg, style: .continuous)
                        .strokeBorder(enabled ? Palette.outline : Palette.outlineVariant, lineWidth: 1)
                )
                .contentShape(Rectangle())
        }
        .buttonStyle(PressStyle())
        .disabled(!enabled)
    }
}

/// A quiet text action: "back", "send again".
struct TextAction: View {
    let label: String
    var enabled = true
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(label)
                .velroFont(.label)
                .foregroundStyle(enabled ? Palette.primary : Palette.disabledLabel)
                .frame(minHeight: Sizing.touchTarget)
                .padding(.horizontal, Spacing.sm)
                .contentShape(Rectangle())
        }
        .buttonStyle(PressStyle())
        .disabled(!enabled)
    }
}

/// Feedback the moment a finger lands, not after the request returns.
struct PressStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .opacity(configuration.isPressed ? 0.75 : 1)
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.98 : 1)
            .animation(reduceMotion ? nil : .easeOut(duration: 0.12), value: configuration.isPressed)
    }
}
