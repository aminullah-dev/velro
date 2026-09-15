import SwiftUI

/// A section's title, an optional line under it, and whatever belongs at its
/// end -- a filter, a count, a refresh button.
///
///     SectionHeader("admin.ops.attention")
///     SectionHeader("admin.ops.week", subtitleKey: "admin.week.trips_title") { Button(...) }
struct SectionHeader<Trailing: View>: View {
    @Environment(\.strings) private var strings
    private let titleKey: String
    private let subtitleKey: String?
    private let trailing: Trailing

    init(_ titleKey: String, subtitleKey: String? = nil, @ViewBuilder trailing: () -> Trailing) {
        self.titleKey = titleKey
        self.subtitleKey = subtitleKey
        self.trailing = trailing()
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: Spacing.s3) {
            VStack(alignment: .leading, spacing: 2) {
                Text(strings[titleKey])
                    .opsFont(.heading, weight: .bold)
                    .foregroundStyle(Palette.text)
                if let subtitleKey {
                    Text(strings[subtitleKey])
                        .opsFont(.caption)
                        .foregroundStyle(Palette.textMuted)
                }
            }
            Spacer(minLength: 0)
            trailing
        }
        .padding(.top, Spacing.s4)
        .padding(.bottom, Spacing.s1)
        .accessibilityAddTraits(.isHeader)
    }
}

extension SectionHeader where Trailing == EmptyView {
    init(_ titleKey: String, subtitleKey: String? = nil) {
        self.init(titleKey, subtitleKey: subtitleKey) { EmptyView() }
    }
}
