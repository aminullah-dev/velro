import SwiftUI
import VelroCore

/// Sign-in or the console, in the chosen language and direction.
struct RootView: View {
    @Environment(OpsModel.self) private var ops

    var body: some View {
        Group {
            if !ops.isSignedIn {
                SignInView(ops: ops)
            } else if ops.roles.isEmpty {
                // Signed in on this device before, roles not known yet: ask
                // before showing a sidebar that might hold nothing.
                ProfileGate()
            } else {
                AppShell()
            }
        }
        // Direction follows the chosen language, not the device's setting.
        .environment(\.layoutDirection, ops.locale.isRTL ? .rightToLeft : .leftToRight)
        .environment(\.locale, Locale(identifier: ops.locale.tag))
        .environment(\.strings, ops.strings)
        .tint(Palette.accent)
        // Whenever the console opens on a session it already holds: is this
        // still somebody with a staff role?
        .task(id: ops.isSignedIn) { [ops] in
            await ops.recheckStaff()
        }
    }
}

/// Waiting for the first `auth/me` on a device that has a session but no
/// roles on record.
private struct ProfileGate: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @State private var error: APIError?

    var body: some View {
        Group {
            if let error {
                VStack(spacing: Spacing.s4) {
                    ErrorView(error: error) { [ops] in
                        self.error = await ops.recheckStaff()
                    }
                    Button(strings["auth.action.sign_out"], role: .destructive) {
                        Task { [ops] in _ = await ops.signOut() }
                    }
                }
            } else {
                LoadingView()
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Palette.background)
        .task { [ops] in
            error = await ops.recheckStaff()
        }
    }
}
