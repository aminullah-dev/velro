import SwiftUI
import VelroCore

/// What a place shows until its feature is built: its name, and a sentence
/// saying so. Each placeholder view in Features/ is one line of this.
struct FeaturePlaceholder: View {
    @Environment(\.strings) private var strings
    let route: Route

    var body: some View {
        VStack(spacing: Spacing.s3) {
            Image(systemName: route.symbol)
                .font(.system(size: 40, weight: .regular))
                .foregroundStyle(Palette.accent)
            Text(strings[route.titleKey])
                .opsFont(.title, weight: .bold)
                .foregroundStyle(Palette.text)
            Text(strings["ops.placeholder.body"])
                .opsFont(.body)
                .foregroundStyle(Palette.textMuted)
        }
        .padding(Spacing.s6)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Palette.background)
        .navigationTitle(strings[route.titleKey])
    }
}
