import SwiftUI
import VelroCore

/// His own account: who VELRO thinks he is, the language, the privacy page,
/// signing out, and deleting the account from inside the app.
struct ProfileView: View {
    @Environment(\.strings) private var strings
    @Environment(\.openURL) private var openURL
    @State private var profile: DriverProfile?
    @State private var account: ProfileDTO?
    @State private var error: APIError?
    @State private var confirmingSignOut = false
    private let app: AppModel

    init(app: AppModel) {
        self.app = app
        _profile = State(initialValue: app.personal.value(DriverProfile.self, key: "driver-me"))
    }

    var body: some View {
        VelroScreen(title: strings["driver.profile.title"]) {
            ScrollView {
                VStack(alignment: .leading, spacing: Spacing.lg) {
                    identity
                    language
                    if let phone = account?.phone {
                        VelroCard {
                            VStack(alignment: .leading, spacing: Spacing.xxs) {
                                Text(strings["passenger.profile.phone"])
                                    .velroFont(.caption)
                                    .foregroundStyle(Palette.onSurfaceVariant)
                                Text(phone)
                                    .font(.body.monospacedDigit())
                                    .foregroundStyle(Palette.onSurface)
                                    .environment(\.layoutDirection, .leftToRight)
                            }
                        }
                    }
                    SecondaryButton(label: strings["driver.documents.title"]) { app.router.open(.documents) }
                    if let error { InlineError(error: error) }
                    SecondaryButton(label: strings["auth.action.sign_out"]) { confirmingSignOut = true }
                        .accessibilityIdentifier("profile.signout")
                        .padding(.top, Spacing.md)
                    VStack(spacing: 0) {
                        TextAction(label: strings["account.privacy"]) { openURL(app.privacyURL) }
                            .accessibilityIdentifier("profile.privacy")
                        TextAction(label: strings["account.delete.action"], destructive: true) {
                            app.router.open(.deleteAccount)
                        }
                        .accessibilityIdentifier("profile.delete")
                    }
                    .frame(maxWidth: .infinity)
                }
                .padding(Spacing.gutter)
            }
        }
        .task { await load() }
        .confirmationDialog(strings["auth.sign_out_warning"], isPresented: $confirmingSignOut, titleVisibility: .visible) {
            Button(strings["auth.action.sign_out"], role: .destructive) { Task { await app.signOut() } }
            Button(strings["common.action.cancel"], role: .cancel) {}
        }
    }

    private var identity: some View {
        VStack(alignment: .leading, spacing: Spacing.md) {
            VStack(spacing: Spacing.sm) {
                Image(systemName: "person.crop.circle.fill")
                    .font(.system(size: 72))
                    .foregroundStyle(Palette.onSurfaceVariant)
                    .accessibilityHidden(true)
                Text((profile?.fullName ?? "").isEmpty ? strings["common.value.no_name"] : profile!.fullName!)
                    .velroFont(.title, weight: .medium)
                    .foregroundStyle(Palette.onSurface)
                if let profile {
                    StatusChip(key: "driver.approval.\(profile.approvalStatus.rawValue.lowercased())",
                               tone: profile.approvalStatus == .approved ? .active : profile.approvalStatus == .pending ? .attention : .failed)
                }
            }
            .frame(maxWidth: .infinity)
            if let profile {
                HStack(spacing: Spacing.sm) {
                    figure(Numerals.localise(String(profile.completedTrips ?? 0), strings.locale), strings["driver.profile.trips"])
                    figure(rating(profile), strings["driver.profile.rating"])
                }
            }
        }
    }

    private var language: some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.sm) {
                Text(strings["passenger.profile.language"])
                    .velroFont(.heading, weight: .medium)
                HStack(spacing: Spacing.sm) {
                    ForEach([AppLocale.dari, .pashto, .english], id: \.self) { locale in
                        ChoiceChip(label: locale.endonym, selected: app.locale == locale) { app.setLocale(locale) }
                    }
                }
            }
            .foregroundStyle(Palette.onSurface)
        }
    }

    private func figure(_ value: String, _ label: String) -> some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.xxs) {
                Text(value)
                    .velroFont(.heading, weight: .bold)
                    .foregroundStyle(Palette.onSurface)
                Text(label)
                    .velroFont(.caption)
                    .foregroundStyle(Palette.onSurfaceVariant)
            }
        }
    }

    private func rating(_ profile: DriverProfile) -> String {
        guard let average = profile.ratingAverage, (profile.ratingCount ?? 0) > 0 else { return strings["driver.profile.no_rating"] }
        return Numerals.localise(String(format: "%.1f", average), strings.locale)
    }

    private func load() async {
        if let fresh = await app.client.send(API.driverProfile(), caching: "driver-me", in: app.personal).value {
            profile = fresh
        }
        switch await app.client.send(API.profile()) {
        case .success(let value): account = value
        case .failure(let failure): if failure != .cancelled && profile == nil { error = failure }
        }
    }
}
