import SwiftUI
import VelroCore

/// The language, and signing this watch out.
struct SettingsPage: View {
    @Environment(WatchModel.self) private var model
    @State private var confirmingSignOut = false

    private static let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "?"
    private static let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "?"

    var body: some View {
        let strings = model.strings
        List {
            Section(strings["passenger.profile.language"]) {
                ForEach(AppLocale.allCases, id: \.self) { locale in
                    Button {
                        model.choose(locale)
                    } label: {
                        HStack {
                            Text(locale.endonym)
                            Spacer()
                            if locale == model.locale {
                                Image(systemName: "checkmark")
                                    .foregroundStyle(WatchPalette.amber)
                            }
                        }
                    }
                }
            }
            Section {
                Button(strings["auth.action.sign_out"], role: .destructive) {
                    confirmingSignOut = true
                }
            } footer: {
                Text(strings["ops.settings.version", ["version": Self.version, "build": Self.build]])
            }
        }
        .navigationTitle(strings["admin.nav.settings"])
        .confirmationDialog(strings["auth.action.sign_out"], isPresented: $confirmingSignOut) {
            Button(strings["auth.action.sign_out"], role: .destructive) { model.signOut() }
            Button(strings["common.action.cancel"], role: .cancel) {}
        }
    }
}
