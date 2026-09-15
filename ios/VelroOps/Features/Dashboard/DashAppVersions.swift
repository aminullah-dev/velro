import SwiftUI
import VelroCore

/// Which versions of the two apps are still being opened
/// (admin/src/components/AppVersions.tsx).
///
/// Launches, not people: one driver opening the app twenty times a day is
/// twenty, and the note above says so, because a number that looks like a
/// head count will be read as one.
struct DashAppVersions: View {
    let apps: AppsReport
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s3) {
            Text(strings["admin.apps.note", ["days": apps.windowDays]])
                .opsFont(.caption)
                .foregroundStyle(Palette.textMuted)
                .fixedSize(horizontal: false, vertical: true)
            LazyVGrid(
                columns: [GridItem(.adaptive(minimum: 320), spacing: Spacing.s3, alignment: .top)],
                alignment: .leading,
                spacing: Spacing.s3
            ) {
                DashAppBlock(app: "passenger", latest: apps.latest?.passenger,
                             rows: apps.versions.filter { $0.app == "passenger" })
                DashAppBlock(app: "driver", latest: apps.latest?.driver,
                             rows: apps.versions.filter { $0.app == "driver" })
            }
        }
    }
}

private struct DashAppBlock: View {
    let app: String
    let latest: AppVersion?
    let rows: [AppVersionCount]

    @Environment(\.strings) private var strings
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let total = rows.reduce(0) { $0 + $1.checks }
        let sorted = rows.sorted {
            $0.versionCode != $1.versionCode ? $0.versionCode > $1.versionCode : $0.platform < $1.platform
        }
        VStack(alignment: .leading, spacing: Spacing.s3) {
            VStack(alignment: .leading, spacing: 2) {
                Text(strings["admin.apps.\(app)"])
                    .opsFont(.heading, weight: .bold)
                    .foregroundStyle(Palette.text)
                    .accessibilityAddTraits(.isHeader)
                Group {
                    if let latest {
                        HStack(spacing: Spacing.s1) {
                            Text(strings["admin.apps.latest"])
                            LTRText("\(latest.versionName) (\(latest.versionCode))")
                        }
                    } else {
                        Text(strings["admin.apps.latest_none"])
                    }
                }
                .opsFont(.caption)
                .foregroundStyle(Palette.textMuted)
            }

            if sorted.isEmpty {
                Text(strings["admin.apps.none"])
                    .opsFont(.label, weight: .regular)
                    .foregroundStyle(Palette.textMuted)
            } else {
                VStack(spacing: 0) {
                    ForEach(Array(sorted.enumerated()), id: \.element.id) { index, row in
                        if index > 0 { Divider() }
                        versionRow(row, total: total)
                            .padding(.vertical, Spacing.s2)
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .opsCard()
    }

    private func versionRow(_ row: AppVersionCount, total: Int) -> some View {
        let share = total > 0 ? Int((Double(row.checks) / Double(total) * 100).rounded()) : 0
        // The published version is the Android release the update check
        // offers; an iOS build number is another count altogether, so an iOS
        // row is shown but never judged against it.
        let current: Bool? = latest.flatMap { latest in
            row.platform == "android" ? row.versionCode >= latest.versionCode : nil
        }
        let platformKey = "admin.apps.platform_\(row.platform)"
        return VStack(alignment: .leading, spacing: Spacing.s1 + 2) {
            HStack(alignment: .firstTextBaseline, spacing: Spacing.s2) {
                LTRText("\(row.versionName) (\(row.versionCode))")
                    .opsFont(.body, weight: .medium)
                    .foregroundStyle(Palette.text)
                Text(strings.has(platformKey) ? strings[platformKey] : row.platform)
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
                Spacer(minLength: Spacing.s2)
                switch current {
                case .some(true): StatusChip(strings["admin.apps.state_latest"], tone: .active)
                case .some(false): StatusChip(strings["admin.apps.state_outdated"], tone: .attention)
                case .none: Text("—").foregroundStyle(Palette.textMuted).accessibilityHidden(true)
                }
            }
            HStack(spacing: Spacing.s2) {
                meter(share)
                    .frame(maxWidth: 160)
                Text(strings["admin.apps.share_value", ["value": share]])
                    .opsFont(.caption, weight: .medium)
                    .foregroundStyle(Palette.text)
                    .monospacedDigit()
                Spacer(minLength: Spacing.s2)
                Text(strings["admin.apps.launches"] + " " + OpsFormat.count(row.checks, strings))
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
                    .monospacedDigit()
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func meter(_ share: Int) -> some View {
        let fill = Color(hex: scheme == .dark ? 0x3987E5 : 0x2A78D6)
        return Capsule()
            .fill(Palette.surfaceMuted)
            .frame(height: 6)
            .overlay(alignment: .leading) {
                GeometryReader { proxy in
                    Capsule()
                        .fill(fill)
                        .frame(width: proxy.size.width * CGFloat(share) / 100)
                }
            }
            .clipShape(Capsule())
            .accessibilityHidden(true)
    }
}
