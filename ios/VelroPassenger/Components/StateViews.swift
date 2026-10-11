import SwiftUI
import VelroCore

// The three states every screen has. No screen ends at "something went
// wrong", and an empty list says why it is empty.

struct LoadingState: View {
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(spacing: Spacing.lg) {
            ProgressView().controlSize(.large).tint(Palette.primary)
            Text(strings["common.state.loading"])
                .velroFont(.label)
                .foregroundStyle(Palette.onSurfaceVariant)
        }
        .frame(maxWidth: .infinity, minHeight: 200)
        .padding(Spacing.xl)
    }
}

struct EmptyState: View {
    let key: String
    var systemImage: String?
    var actionKey: String?
    var action: (() -> Void)?
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(spacing: Spacing.lg) {
            if let systemImage {
                Image(systemName: systemImage)
                    .font(.system(size: 32))
                    .foregroundStyle(Palette.onSurfaceVariant)
                    .accessibilityHidden(true)
            }
            Text(strings[key])
                .velroFont(.body)
                .foregroundStyle(Palette.onSurfaceVariant)
                .multilineTextAlignment(.center)
            if let actionKey, let action {
                TextAction(label: strings[actionKey], action: action)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 200)
        .padding(Spacing.xl)
    }
}

/// A failure the person can act on: a weak connection says so, and there is
/// always a way to try again.
struct ErrorState: View {
    let error: APIError
    var retry: (() -> Void)?
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(spacing: Spacing.lg) {
            Text(strings.forErrorCode(error.code, context: error.context.arguments))
                .velroFont(.body)
                .foregroundStyle(Palette.onSurface)
                .multilineTextAlignment(.center)
            if let retry {
                SecondaryButton(label: strings["common.action.retry"], action: retry)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 200)
        .padding(Spacing.xl)
    }
}

/// A pushed screen's frame: the page ground, a title in the bar, the
/// gutter. Home is the only screen without one.
struct VelroScreen<Content: View>: View {
    let title: String
    @ViewBuilder var content: Content

    var body: some View {
        content
            // On an unfolded phone the form stays a column, centred.
            .frame(maxWidth: Wide.readable, maxHeight: .infinity, alignment: .top)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            .background(Palette.background)
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            // No bar of its own: the title sits on the page it names, and the
            // back button floats, as on a sheet.
            .toolbarBackground(Palette.background, for: .navigationBar)
            .toolbar {
                // The bar's own title is the system face; the product's
                // letters -- Vazirmatn in Dari and Pashto -- are drawn here.
                ToolbarItem(placement: .principal) {
                    Text(title)
                        .velroFont(.heading, weight: .bold)
                        .foregroundStyle(Palette.onSurface)
                        .lineLimit(1)
                        .accessibilityAddTraits(.isHeader)
                }
            }
    }
}
