import SwiftUI
import VelroCore

/// Leaving VELRO altogether, from the same screen she opened the account on.
///
/// Said plainly before it happens: what goes, what stays and why, and that the
/// same number can start again. Then one button and one question. A refusal --
/// a seat still booked for her -- is shown here, in the words the server
/// chose, because it is something she can go and fix.
struct DeleteAccountView: View {
    @Environment(\.strings) private var strings
    @State private var confirming = false
    @State private var isDeleting = false
    @State private var error: APIError?
    private let app: AppModel

    init(app: AppModel) { self.app = app }

    var body: some View {
        VelroScreen(title: strings["account.delete.title"]) {
            ScrollView {
                VStack(alignment: .leading, spacing: Spacing.lg) {
                    VelroCard {
                        part(
                            symbol: "trash",
                            tint: Palette.error,
                            title: strings["account.delete.gone_title"],
                            text: strings["account.delete.gone"]
                        )
                    }
                    VelroCard {
                        part(
                            symbol: "archivebox",
                            tint: Palette.onSurfaceVariant,
                            title: strings["account.delete.kept_title"],
                            text: strings["account.delete.kept"]
                        )
                    }
                    Text(strings["account.delete.again"])
                        .velroFont(.caption)
                        .foregroundStyle(Palette.onSurfaceVariant)
                        .fixedSize(horizontal: false, vertical: true)

                    if let error { InlineError(error: error) }

                    DestructiveButton(label: strings["account.delete.action"], loading: isDeleting) {
                        confirming = true
                    }
                    .accessibilityIdentifier("account.delete.start")
                    SecondaryButton(label: strings["common.action.cancel"]) { app.router.back() }
                        .disabled(isDeleting)
                }
                .padding(Spacing.gutter)
            }
        }
        // An alert, not a sheet from the bottom: this is the one tap in the
        // app that cannot be undone, and it should stop her in the middle of
        // the screen rather than sit where a thumb already is.
        .alert(strings["account.delete.confirm_question"], isPresented: $confirming) {
            Button(strings["account.delete.confirm"], role: .destructive) { Task { await delete() } }
                .accessibilityIdentifier("account.delete.confirm")
            Button(strings["common.action.cancel"], role: .cancel) {}
        }
    }

    private func part(symbol: String, tint: Color, title: String, text: String) -> some View {
        HStack(alignment: .top, spacing: Spacing.md) {
            Image(systemName: symbol)
                .font(.title3)
                .foregroundStyle(tint)
                .frame(width: 28)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: Spacing.xs) {
                Text(title)
                    .velroFont(.heading, weight: .medium)
                    .foregroundStyle(Palette.onSurface)
                Text(text)
                    .velroFont(.body)
                    .foregroundStyle(Palette.onSurfaceVariant)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func delete() async {
        isDeleting = true
        error = nil
        switch await app.client.send(API.deleteAccount()) {
        case .success:
            app.accountWasDeleted()
        case .failure(let failure):
            if failure != .cancelled { error = failure }
        }
        isDeleting = false
    }
}
