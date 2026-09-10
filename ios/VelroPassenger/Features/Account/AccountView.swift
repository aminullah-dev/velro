import SwiftUI
import VelroCore

/// Her own account: her name, the language the app speaks to her in, how
/// often she has travelled, and the way out.
///
/// The language matters most. Chosen once on the sign-in screen and then
/// driving everything, it could lock somebody whose phone was set up by a son
/// or a neighbour into a language she cannot read. No badges and no tiers:
/// this is a screen for changing a name and a language.
struct AccountView: View {
    @Environment(\.strings) private var strings
    @State private var profile: ProfileDTO?
    @State private var draftName = ""
    @State private var isSaving = false
    @State private var saved = false
    @State private var error: APIError?
    @State private var confirmingSignOut = false
    private let app: AppModel

    init(app: AppModel) { self.app = app }

    var body: some View {
        VelroScreen(title: strings["passenger.profile.title"]) {
            if let profile {
                ScrollView { content(profile).padding(Spacing.gutter) }
            } else if let error {
                ErrorState(error: error) { Task { await load() } }
            } else {
                LoadingState()
            }
        }
        .task { await load() }
        // Confirmed, because it wipes her journeys from the phone and signing
        // back in needs a connection she may not have.
        .confirmationDialog(strings["auth.sign_out_warning"], isPresented: $confirmingSignOut, titleVisibility: .visible) {
            Button(strings["auth.action.sign_out"], role: .destructive) { Task { await app.signOut() } }
                .accessibilityIdentifier("account.signout.confirm")
            Button(strings["common.action.cancel"], role: .cancel) {}
        }
    }

    private func content(_ profile: ProfileDTO) -> some View {
        VStack(alignment: .leading, spacing: Spacing.lg) {
            // A silhouette with no way to change it: a passenger is not asked
            // for her photograph before she can travel.
            VStack(spacing: Spacing.md) {
                DriverAvatar(photo: nil, size: 96)
                Text((profile.fullName ?? "").isEmpty ? strings["common.value.no_name"] : profile.fullName!)
                    .velroFont(.title, weight: .medium)
                    .foregroundStyle(Palette.onSurface)
            }
            .frame(maxWidth: .infinity)

            HStack(spacing: Spacing.sm) {
                figure(Numerals.format(profile.completedTrips ?? 0, strings.locale), strings["passenger.profile.trips"])
                // A dash, not 0.0, until a driver has scored her: 0.0 reads as
                // a bad passenger rather than a new one.
                figure(rating(profile), strings["driver.profile.rating"])
                figure(ISODate.parse(profile.memberSince).map { Calendars.date($0, strings.locale) } ?? "—",
                       strings["passenger.profile.since"])
            }

            VelroCard {
                VStack(alignment: .leading, spacing: Spacing.md) {
                    VelroField(label: strings["profile.field.name"], text: $draftName, identifier: "account.name")
                    Text(strings["profile.hint.name_optional"])
                        .velroFont(.caption)
                        .foregroundStyle(Palette.onSurfaceVariant)
                    PrimaryButton(label: strings["common.action.save"],
                                  enabled: draftName != (profile.fullName ?? ""), loading: isSaving, pill: true) {
                        Task { await saveName() }
                    }
                    if saved {
                        Text(strings["passenger.profile.name_saved"])
                            .velroFont(.caption)
                            .foregroundStyle(Palette.primary)
                    }
                }
            }

            VelroCard {
                VStack(alignment: .leading, spacing: Spacing.sm) {
                    Text(strings["passenger.profile.language"])
                        .velroFont(.heading, weight: .medium)
                    Text(strings["passenger.profile.language_hint"])
                        .velroFont(.caption)
                        .foregroundStyle(Palette.onSurfaceVariant)
                    HStack(spacing: Spacing.sm) {
                        ForEach([AppLocale.dari, .pashto, .english], id: \.self) { locale in
                            ChoiceChip(label: locale.endonym, selected: app.locale == locale) { app.setLocale(locale) }
                        }
                    }
                }
                .foregroundStyle(Palette.onSurface)
            }

            VelroCard {
                VStack(alignment: .leading, spacing: Spacing.xxs) {
                    Text(strings["passenger.profile.phone"])
                        .velroFont(.caption)
                        .foregroundStyle(Palette.onSurfaceVariant)
                    Text(profile.phone)
                        .font(.body.monospacedDigit())
                        .foregroundStyle(Palette.onSurface)
                        .environment(\.layoutDirection, .leftToRight)
                    Text(strings["passenger.profile.phone_hint"])
                        .velroFont(.caption)
                        .foregroundStyle(Palette.onSurfaceVariant)
                        .padding(.top, Spacing.xs)
                }
            }

            if let error { InlineError(error: error) }

            // Last: somewhere she goes on purpose, after what she came for.
            SecondaryButton(label: strings["auth.action.sign_out"]) { confirmingSignOut = true }
                .accessibilityIdentifier("account.signout")
                .padding(.top, Spacing.md)
        }
    }

    private func figure(_ value: String, _ label: String) -> some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.xxs) {
                Text(value)
                    .velroFont(.heading, weight: .bold)
                    .foregroundStyle(Palette.onSurface)
                    .lineLimit(1)
                    .minimumScaleFactor(0.7)
                Text(label)
                    .velroFont(.caption)
                    .foregroundStyle(Palette.onSurfaceVariant)
            }
        }
    }

    private func rating(_ profile: ProfileDTO) -> String {
        guard let average = profile.ratingAverage, (profile.ratingCount ?? 0) > 0 else { return "—" }
        return Numerals.localise(String(format: "%.1f", average), strings.locale)
    }

    private func load() async {
        error = nil
        switch await app.client.send(API.profile()) {
        case .success(let value):
            profile = value
            draftName = value.fullName ?? ""
        case .failure(let failure):
            if failure != .cancelled { error = failure }
        }
    }

    private func saveName() async {
        isSaving = true
        saved = false
        let name = draftName.trimmingCharacters(in: .whitespacesAndNewlines)
        switch await app.client.send(API.updateProfile(fullName: name)) {
        case .success(let value):
            profile = value
            draftName = value.fullName ?? ""
            saved = true
        case .failure(let failure):
            if failure != .cancelled { error = failure }
        }
        isSaving = false
    }
}
