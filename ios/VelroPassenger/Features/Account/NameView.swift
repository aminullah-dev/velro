import SwiftUI
import VelroCore

/// The step between signing up and home: a first and a last name, both
/// required. The driver sees it on the request and calls it out at the
/// roadside, so a journey never starts with a stranger.
///
/// It cannot be skipped -- the owner's rule -- only left by signing out, for
/// the person who typed the wrong number.
struct NameView: View {
    @Environment(\.strings) private var strings
    @State private var first = ""
    @State private var last = ""
    @State private var isSaving = false
    @State private var tried = false
    @State private var error: APIError?
    private let app: AppModel

    init(app: AppModel) { self.app = app }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.xl) {
                Text(strings["app.name"])
                    .velroFont(.heading, weight: .bold)
                    .foregroundStyle(Palette.primary)

                VStack(alignment: .leading, spacing: Spacing.sm) {
                    Text(strings["profile.name.title"])
                        .velroFont(.hero)
                        .foregroundStyle(Palette.onSurface)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                    Text(strings["profile.name.body"])
                        .velroFont(.body)
                        .foregroundStyle(Palette.onSurfaceVariant)
                        .fixedSize(horizontal: false, vertical: true)
                }

                NameFields(first: $first, last: $last)

                if tried && !NameFields.isValid(first: first, last: last) {
                    Label(strings["profile.error.name_required"], systemImage: "exclamationmark.circle.fill")
                        .velroFont(.label)
                        .foregroundStyle(Palette.error)
                        .accessibilityIdentifier("name.required")
                }
                if let error { InlineError(error: error) }

                PrimaryButton(label: strings["common.action.continue"], loading: isSaving) {
                    Task { await save() }
                }
                .accessibilityIdentifier("name.continue")

                // The way out for a wrong number, quiet and below the one
                // thing the screen is for.
                TextAction(label: strings["auth.action.sign_out"]) {
                    Task { await app.signOut() }
                }
                .frame(maxWidth: .infinity)
                .accessibilityIdentifier("name.signout")
            }
            .padding(.horizontal, Spacing.gutter)
            .padding(.vertical, Spacing.xl)
            .frame(maxWidth: Wide.readable)
            .frame(maxWidth: .infinity)
        }
        .scrollDismissesKeyboard(.interactively)
        .background(Palette.background)
    }

    private func save() async {
        tried = true
        guard NameFields.isValid(first: first, last: last) else { return }
        isSaving = true
        error = nil
        let result = await app.client.send(API.updateProfile(fullName: NameFields.join(first: first, last: last)))
        isSaving = false
        switch result {
        case .success(let profile): app.nameChanged(profile.fullName)
        case .failure(let failure): if failure != .cancelled { error = failure }
        }
    }
}

/// A first and a last name, as two fields. Shared by the step above and the
/// account screen, so the rule is written once.
struct NameFields: View {
    @Binding var first: String
    @Binding var last: String
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.lg) {
            VelroField(
                label: strings["profile.field.first_name"],
                text: $first,
                contentType: .givenName,
                systemImage: "person.fill",
                leftToRight: false,
                identifier: "name.first"
            )
            VelroField(
                label: strings["profile.field.last_name"],
                text: $last,
                contentType: .familyName,
                systemImage: "person.2.fill",
                leftToRight: false,
                identifier: "name.last"
            )
        }
    }

    /// Two letters each at least: one is an initial, not a name a driver can
    /// call out.
    static func isValid(first: String, last: String) -> Bool {
        clean(first).count >= 2 && clean(last).count >= 2
    }

    static func join(first: String, last: String) -> String {
        clean(first) + " " + clean(last)
    }

    /// The stored name back into its two parts: the first word, and the rest.
    static func split(_ fullName: String?) -> (first: String, last: String) {
        let words = (fullName ?? "").split(whereSeparator: \.isWhitespace).map(String.init)
        guard let head = words.first else { return ("", "") }
        return (head, words.dropFirst().joined(separator: " "))
    }

    private static func clean(_ part: String) -> String {
        part.split(whereSeparator: \.isWhitespace).joined(separator: " ")
    }
}
