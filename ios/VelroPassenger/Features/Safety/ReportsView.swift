import SwiftUI
import VelroCore

/// The reports she has raised, and what VELRO said back. Without this a report
/// is a one-way door: the answer is written and nothing on the phone opens it.
struct ReportsView: View {
    @Environment(\.strings) private var strings
    @State private var reports: [Ticket] = []
    @State private var isLoading = true
    @State private var error: APIError?
    @State private var openId: String?
    @State private var draft = ""
    @State private var sending = false
    @State private var replyError: APIError?
    private let app: AppModel

    init(app: AppModel) { self.app = app }

    var body: some View {
        VelroScreen(title: strings["safety.my_reports"]) {
            if isLoading && reports.isEmpty {
                LoadingState()
            } else if let error, reports.isEmpty {
                ErrorState(error: error) { Task { await load() } }
            } else if reports.isEmpty {
                EmptyState(key: "safety.no_reports", systemImage: "tray")
            } else {
                ScrollView {
                    LazyVStack(spacing: Spacing.sm) {
                        ForEach(reports) { report in card(report) }
                    }
                    .padding(Spacing.gutter)
                }
                .refreshable { await load() }
            }
        }
        .task { await load() }
    }

    private func card(_ report: Ticket) -> some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.sm) {
                Button {
                    // Another report drops the draft: words typed under one
                    // reference must not be sent into another.
                    openId = openId == report.id ? nil : report.id
                    draft = ""
                    replyError = nil
                } label: {
                    VStack(alignment: .leading, spacing: Spacing.xs) {
                        HStack {
                            // Latin and unmirrored: read down a phone line.
                            Text(report.reference)
                                .font(.subheadline.monospaced().weight(.semibold))
                                .environment(\.layoutDirection, .leftToRight)
                            Spacer()
                            StatusChip(key: statusKey(report.status), tone: report.hasAnswer ? .active : .neutral)
                        }
                        Text(TicketCategory.label(report.categoryCode, strings))
                            .velroFont(.label)
                            .foregroundStyle(Palette.onSurfaceVariant)
                        if !report.hasAnswer {
                            Text(strings["safety.awaiting_answer"])
                                .velroFont(.caption)
                                .foregroundStyle(Palette.onSurfaceVariant)
                        }
                    }
                    .foregroundStyle(Palette.onSurface)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)

                if openId == report.id { conversation(report) }
            }
        }
    }

    @ViewBuilder
    private func conversation(_ report: Ticket) -> some View {
        Divider()
        ForEach(report.messages ?? []) { message in
            let mine = message.isFromReporter ?? true
            VStack(alignment: .leading, spacing: Spacing.xxs) {
                Text(strings[mine ? "safety.from_you" : "safety.from_velro"])
                    .velroFont(.caption, weight: .medium)
                    .foregroundStyle(mine ? Palette.onSurfaceVariant : Palette.primary)
                Text(message.body)
                    .velroFont(.label)
                    .foregroundStyle(Palette.onSurface)
                if let sent = ISODate.parse(message.sentAt) {
                    Text(Calendars.dateTime(sent, strings.locale))
                        .velroFont(.caption)
                        .foregroundStyle(Palette.onSurfaceVariant)
                }
            }
            .padding(Spacing.sm)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(mine ? Palette.surfaceVariant : Palette.primaryContainer, in: RoundedRectangle(cornerRadius: Radius.md))
        }
        if report.canReply {
            VelroField(label: strings["safety.reply_placeholder"], text: $draft)
            if let replyError { InlineError(error: replyError) }
            PrimaryButton(label: strings["safety.reply"],
                          enabled: !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                          loading: sending) {
                Task { await reply(report.id) }
            }
        } else {
            Text(strings["safety.closed_note"])
                .velroFont(.caption)
                .foregroundStyle(Palette.onSurfaceVariant)
        }
    }

    private func statusKey(_ status: TicketStatus) -> String {
        switch status {
        case .open: "ticket.status.open"
        case .inProgress: "ticket.status.in_progress"
        case .resolved: "ticket.status.resolved"
        case .closed: "ticket.status.closed"
        }
    }

    private func load() async {
        switch await app.client.send(API.myTickets()) {
        case .success(let value):
            reports = value
            error = nil
        case .failure(let failure):
            if failure != .cancelled { error = failure }
        }
        isLoading = false
    }

    /// Re-read after replying rather than appending locally: her reply can
    /// pull an answered report back open, and the server decides that.
    private func reply(_ id: String) async {
        let body = draft.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !body.isEmpty, !sending else { return }
        sending = true
        replyError = nil
        switch await app.client.send(API.reply(toTicket: id, body: body)) {
        case .success:
            draft = ""
            await load()
        case .failure(let failure):
            if failure != .cancelled { replyError = failure }
        }
        sending = false
    }
}
