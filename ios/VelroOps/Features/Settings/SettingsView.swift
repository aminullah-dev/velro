import SwiftUI
import VelroCore

/// The console's own settings: the language, who is signed in and with which
/// roles, and signing out. (The server's settings are the admin panel's
/// Settings page; they are not here.)
struct SettingsView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @State private var confirm: ConfirmRequest?

    var body: some View {
        @Bindable var ops = ops
        Form {
            Section {
                Picker(strings["passenger.profile.language"], selection: $ops.locale) {
                    ForEach(AppLocale.allCases, id: \.self) { locale in
                        Text(locale.endonym).tag(locale)
                    }
                }
                .pickerStyle(.segmented)
                .accessibilityIdentifier("settings.language")
            } header: {
                Text(strings["passenger.profile.language"])
            } footer: {
                Text(strings["passenger.profile.language_hint"])
            }

            Section {
                LabeledContent(strings["admin.col.name"]) {
                    Text(ops.profile?.fullName ?? strings["common.value.no_name"])
                }
                LabeledContent(strings["admin.col.phone"]) {
                    LTRText(ops.profile?.phone ?? "—")
                }
                LabeledContent(strings["ops.settings.roles"]) {
                    HStack(spacing: Spacing.s1) {
                        ForEach(ops.access.staffRoles, id: \.self) { role in
                            StatusChip(role: role.rawValue)
                        }
                    }
                }
            } header: {
                Text(strings["passenger.profile.title"])
            }

            Section {
                Button(strings["auth.action.sign_out"], role: .destructive) {
                    Task { [ops] in _ = await ops.signOut() }
                }
                .accessibilityIdentifier("settings.sign_out")
                Button(strings["auth.action.sign_out_all"], role: .destructive) {
                    confirm = ConfirmRequest(
                        title: strings["auth.action.sign_out_all"],
                        confirmTitle: strings["auth.action.sign_out_all"],
                        isDestructive: true
                    ) { [ops] _ in
                        await ops.signOut(allDevices: true)
                    }
                }
            } footer: {
                Text(strings["ops.settings.version", ["version": Self.version, "build": Self.build]])
            }
        }
        .formStyle(.grouped)
        .navigationTitle(strings["admin.nav.settings"])
        .confirmAction($confirm)
    }

    private static let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "—"
    private static let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "—"
}
