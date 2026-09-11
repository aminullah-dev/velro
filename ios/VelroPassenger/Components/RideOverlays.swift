import SwiftUI
import VelroCore

/// The road's next warning, at the top of the ride map: the warning itself
/// once the car is in it, and how far off it is before. Nothing at all when
/// the road ahead is clear or the car's position is unknown -- an empty
/// banner would read as a warning about nothing.
struct RoadAheadBanner: View {
    let next: RoadAhead.Next?
    @Environment(\.strings) private var strings

    var body: some View {
        Group {
            if let next {
                HStack(alignment: .top, spacing: Spacing.sm) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(next.inside ? Palette.onToneAttention : Palette.accent)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: Spacing.xxs) {
                        Text(strings["notif.road.title"])
                            .velroFont(.caption, weight: .medium)
                            .foregroundStyle(Palette.onSurfaceVariant)
                        Text(strings[next.messageKey])
                            .velroFont(.label, weight: .medium)
                            .foregroundStyle(Palette.onSurface)
                        if !next.inside {
                            Text(distance(next.metres))
                                .velroFont(.caption)
                                .foregroundStyle(Palette.onSurfaceVariant)
                        }
                    }
                    Spacer(minLength: 0)
                }
                .padding(Spacing.md)
                .background(next.inside ? Palette.toneAttention : Palette.surface,
                            in: RoundedRectangle(cornerRadius: Radius.lg, style: .continuous))
                .shadow(color: .black.opacity(0.15), radius: 6, y: 2)
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("ride.road")
            } else {
                Color.clear.frame(height: 1)
            }
        }
        .frame(maxWidth: .infinity)
        .animation(.easeOut(duration: 0.2), value: next)
    }

    private func distance(_ metres: Int) -> String {
        metres >= 1000
            ? strings["location.distance.kilometres", ["distance": metres / 1000]]
            : strings["location.distance.metres", ["distance": metres]]
    }
}

/// Who is in the car, and nothing else, at the foot of the ride map.
struct RideNames: View {
    let driver: String?
    let passenger: String?
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(spacing: Spacing.sm) {
            row(strings["trip.label.driver"], driver)
            Divider()
            row(strings["driver.label.passengers"], passenger)
        }
        .padding(Spacing.lg)
        .background(Palette.surface, in: RoundedRectangle(cornerRadius: Radius.card, style: .continuous))
        .shadow(color: .black.opacity(0.15), radius: 8, y: 2)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("ride.names")
    }

    private func row(_ label: String, _ name: String?) -> some View {
        HStack {
            Text(label)
                .velroFont(.label)
                .foregroundStyle(Palette.onSurfaceVariant)
            Spacer()
            Text((name ?? "").isEmpty ? strings["common.value.no_name"] : name!)
                .velroFont(.heading, weight: .medium)
                .foregroundStyle(Palette.onSurface)
        }
    }
}
