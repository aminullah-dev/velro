import SwiftUI
import VelroCore

/// Waiting for the first answer. (Refreshing an answer already on screen
/// should not replace it with this.)
struct LoadingView: View {
    @Environment(\.strings) private var strings
    private let labelKey: String

    init(labelKey: String = "common.state.loading") { self.labelKey = labelKey }

    var body: some View {
        VStack(spacing: Spacing.s3) {
            ProgressView()
            Text(strings[labelKey])
                .opsFont(.label, weight: .regular)
                .foregroundStyle(Palette.textMuted)
        }
        .padding(Spacing.s6)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// A list with nothing in it -- said in words, because an empty list and a
/// failed one must never look alike. (Named so, not `EmptyView`, which is
/// SwiftUI's.)
///
///     EmptyStateView(messageKey: "admin.empty.unassigned", systemImage: "checkmark.circle")
struct EmptyStateView: View {
    @Environment(\.strings) private var strings
    private let messageKey: String
    private let systemImage: String

    init(messageKey: String, systemImage: String = "tray") {
        self.messageKey = messageKey
        self.systemImage = systemImage
    }

    var body: some View {
        VStack(spacing: Spacing.s3) {
            Image(systemName: systemImage)
                .font(.system(size: 32))
                .foregroundStyle(Palette.textMuted)
            Text(strings[messageKey])
                .opsFont(.body)
                .foregroundStyle(Palette.textMuted)
                .multilineTextAlignment(.center)
        }
        .padding(Spacing.s6)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// A request that failed: why, in the reader's language, the reference
/// support will ask for, and a way to try again.
///
///     ErrorView(error: error) { await model.load() }
struct ErrorView: View {
    @Environment(\.strings) private var strings
    private let error: APIError
    private let retry: (@MainActor () async -> Void)?
    @State private var isRetrying = false

    init(error: APIError, retry: (@MainActor () async -> Void)? = nil) {
        self.error = error
        self.retry = retry
    }

    private var isOffline: Bool { error.code == APIError.offlineCode }

    var body: some View {
        VStack(spacing: Spacing.s3) {
            Image(systemName: isOffline ? "wifi.slash" : "exclamationmark.triangle")
                .font(.system(size: 32))
                .foregroundStyle(isOffline ? Palette.attention : Palette.danger)
            Text(strings.forErrorCode(error.code, context: error.context.arguments))
                .opsFont(.body)
                .foregroundStyle(Palette.text)
                .multilineTextAlignment(.center)
            if let reference = error.requestId {
                Text(strings["ops.error.reference", ["id": reference]])
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
                    .textSelection(.enabled)
            }
            if retry != nil {
                Button {
                    Task { await runRetry() }
                } label: {
                    if isRetrying {
                        ProgressView().controlSize(.small)
                    } else {
                        Text(strings["common.action.retry"])
                    }
                }
                .buttonStyle(.bordered)
                .disabled(isRetrying)
            }
        }
        .padding(Spacing.s6)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func runRetry() async {
        guard let retry else { return }
        isRetrying = true
        await retry()
        isRetrying = false
    }
}

/// A line of news above the content: an error, a confirmation, a warning.
struct Banner: View {
    enum Tone { case error, info, warning }

    private let text: String
    private let tone: Tone
    private let systemImage: String?

    init(_ text: String, tone: Tone = .error, systemImage: String? = nil) {
        self.text = text
        self.tone = tone
        self.systemImage = systemImage
    }

    private var colors: (Color, Color) {
        switch tone {
        case .error: (Palette.bannerError, Palette.onBannerError)
        case .info: (Palette.bannerInfo, Palette.onBannerInfo)
        case .warning: (Palette.bannerWarning, Palette.onBannerWarning)
        }
    }

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: Spacing.s2) {
            if let systemImage { Image(systemName: systemImage) }
            Text(text)
                .opsFont(.label, weight: .regular)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, Spacing.s4)
        .padding(.vertical, Spacing.s3)
        .foregroundStyle(colors.1)
        .background(colors.0, in: RoundedRectangle(cornerRadius: Radius.md, style: .continuous))
    }
}

/// The server cannot be reached. The shell shows it above every screen, so
/// a figure left on screen is never mistaken for a current one.
struct OfflineBanner: View {
    @Environment(\.strings) private var strings

    var body: some View {
        HStack(spacing: Spacing.s2) {
            Image(systemName: "wifi.slash")
            Text(strings["ops.offline.banner"])
                .opsFont(.label, weight: .medium)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, Spacing.s4)
        .padding(.vertical, Spacing.s2)
        .foregroundStyle(Palette.onBannerWarning)
        .background(Palette.bannerWarning)
        .accessibilityElement(children: .combine)
    }
}
