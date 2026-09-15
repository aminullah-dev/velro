import SwiftUI
import VelroCore

extension EnvironmentValues {
    /// The text in the chosen language. Every screen reads its words from
    /// here -- `strings["admin.nav.trips"]` -- and no user-visible literal
    /// appears anywhere else in the app.
    @Entry var strings = Strings(locale: .dari, translations: [:], fallback: [:])
}
