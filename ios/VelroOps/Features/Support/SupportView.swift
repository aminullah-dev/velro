import Observation
import SwiftUI
import VelroCore

/// The support queue (the panel's Support.tsx).
///
/// The order is the triage and comes from the server -- urgent first, then
/// oldest -- and this screen never re-sorts it: a safety report raised at
/// 02:00 must not be pushed down by a fare dispute raised at 09:00.
///
/// Other screens open it with `navigator.open(.support, filter:)`: "working",
/// "open", "in_progress", "resolved", "closed", "all", "urgent",
/// "category:<CODE>", "ticket:<id>" (selects it).
struct SupportView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @State private var model = OpSupportModel()
    @State private var selectedID: String?
    /// A request another screen asked for ("ticket:<id>"), pushed on an iPhone.
    @State private var pushedID: String?

    init() {}

    var body: some View {
        OpSplitReader { isSplit in
            if isSplit {
                OpSplitLayout(listWidth: 420) {
                    list(isSplit: true)
                } detail: {
                    if let id = selectedID {
                        OpTicketDetailView(ticketId: id, initial: model.ticket(id)) { [model, ops] in await model.load(ops) }
                            .id(id)
                    } else {
                        OpNothingSelected(messageKey: "ops.support.choose", systemImage: "lifepreserver")
                    }
                }
            } else {
                list(isSplit: false)
                    .navigationDestination(for: AdminTicket.self) { ticket in
                        OpTicketDetailView(ticketId: ticket.id, initial: ticket) { [model, ops] in await model.load(ops) }
                    }
                    // It loads itself by id: a closed request is not in the
                    // working queue, and is still the one that was asked for.
                    .navigationDestination(item: $pushedID) { id in
                        OpTicketDetailView(ticketId: id, initial: model.ticket(id)) { [model, ops] in await model.load(ops) }
                    }
            }
        }
        .background(Palette.background)
        .navigationTitle(strings["admin.support.title"])
        .toolbar {
            ToolbarItemGroup(placement: .primaryAction) {
                Menu {
                    Picker(strings["admin.col.category"], selection: categoryBinding) {
                        Text(strings["admin.filter.all"]).tag(String?.none)
                        ForEach(OpSupportModel.categories, id: \.self) { code in
                            Text(OpText.word("ticket.category." + code.lowercased(), raw: code, strings)).tag(String?.some(code))
                        }
                    }
                    .pickerStyle(.inline)
                } label: {
                    Label(strings["admin.col.category"], systemImage: model.category == nil
                          ? "line.3.horizontal.decrease.circle" : "line.3.horizontal.decrease.circle.fill")
                }
                OpRefreshButton { [model, ops] in await model.load(ops) }
            }
        }
        .task { [model, ops] in
            let chosen = model.apply(deepLink: ops.navigator.takeFilter(for: .support))
            if let chosen { selectedID = chosen }
            await model.load(ops)
            // On an iPhone it is opened once the queue stands behind it.
            if let chosen { pushedID = chosen }
        }
        // Short, because this is the queue somebody watches on shift.
        .poll(every: .seconds(30)) { [model, ops] in
            if case .loaded = model.state { await model.load(ops) }
        }
    }

    private var categoryBinding: Binding<String?> {
        Binding(get: { model.category }, set: { value in
            model.category = value
            Task { [model, ops] in await model.restart(ops) }
        })
    }

    private var filterBinding: Binding<OpSupportModel.Filter> {
        Binding(get: { model.filter }, set: { value in
            guard value != model.filter else { return }
            model.filter = value
            Task { [model, ops] in await model.restart(ops) }
        })
    }

    @ViewBuilder
    private func list(isSplit: Bool) -> some View {
        VStack(spacing: 0) {
            OpChipBar(options: OpSupportModel.Filter.allCases.map { .init(value: $0, label: $0.label(strings)) },
                      selection: filterBinding)
            if let queue = model.state.value {
                HStack(spacing: Spacing.s2) {
                    StatusChip(strings["admin.support.open_count", ["count": queue.open]], tone: .attention)
                    if queue.urgentOpen > 0 {
                        StatusChip(strings["admin.support.urgent_count", ["count": queue.urgentOpen]], tone: .failed)
                    }
                    Spacer(minLength: 0)
                    Toggle(strings["admin.support.urgent"], isOn: Binding(get: { model.onlyUrgent }, set: { model.onlyUrgent = $0 }))
                        .toggleStyle(.button)
                        .controlSize(.small)
                        .opsFont(.caption)
                }
                .padding(.horizontal, Spacing.s4)
                .padding(.bottom, Spacing.s2)
            }
            if let category = model.category {
                HStack(spacing: Spacing.s2) {
                    Text(strings["admin.col.category"])
                        .foregroundStyle(Palette.textMuted)
                    StatusChip(OpText.word("ticket.category." + category.lowercased(), raw: category, strings))
                    Button {
                        categoryBinding.wrappedValue = nil
                    } label: {
                        Image(systemName: "xmark.circle.fill").accessibilityLabel(strings["admin.filter.all"])
                    }
                    .buttonStyle(.borderless)
                    Spacer(minLength: 0)
                }
                .opsFont(.caption)
                .padding(.horizontal, Spacing.s4)
                .padding(.bottom, Spacing.s2)
            }
            Divider()
            switch model.state {
            case .loading:
                LoadingView()
            case .failed(let error):
                ErrorView(error: error) { [model, ops] in await model.load(ops) }
            case .loaded(let queue):
                let shown = model.onlyUrgent ? queue.tickets.filter(\.isUrgent) : queue.tickets
                if shown.isEmpty {
                    EmptyStateView(messageKey: "admin.support.none", systemImage: "lifepreserver")
                } else {
                    List(selection: isSplit ? $selectedID : .constant(nil)) {
                        Section {
                            ForEach(shown) { ticket in
                                Group {
                                    if isSplit {
                                        OpTicketRowView(ticket: ticket).tag(ticket.id)
                                    } else {
                                        NavigationLink(value: ticket) { OpTicketRowView(ticket: ticket) }
                                    }
                                }
                                .opAttentionRow(ticket.isUrgent && ticket.status == .open)
                            }
                        } footer: {
                            Text(strings["admin.support.subtitle"])
                                .opsFont(.caption)
                                .foregroundStyle(Palette.textMuted)
                                .padding(.vertical, Spacing.s2)
                        }
                    }
                    .listStyle(.plain)
                    // Selected beside its detail: a light ground the row's own ink reads on.
                    .tint(isSplit ? Palette.bannerInfo : Palette.accent)
                    .scrollContentBackground(.hidden)
                    .refreshable { [model, ops] in await model.load(ops) }
                }
            }
        }
    }
}

// MARK: - The model

@MainActor
@Observable
final class OpSupportModel {
    enum Filter: CaseIterable, Hashable {
        case working, open, inProgress, resolved, closed, all

        var query: SupportQueueFilter {
            switch self {
            case .working: .working
            case .open: .only(.open)
            case .inProgress: .only(.inProgress)
            case .resolved: .only(.resolved)
            case .closed: .only(.closed)
            // Sent as ALL, never omitted: omitting it is the working queue,
            // and a button labelled All that hid every answered request is
            // the bug Support.tsx records.
            case .all: .all
            }
        }

        func label(_ strings: Strings) -> String {
            switch self {
            case .working: strings["ops.support.working"]
            case .open: strings["admin.support.filter_open"]
            case .inProgress: strings["admin.support.filter_in_progress"]
            case .resolved: strings["ticket.status.resolved"]
            case .closed: strings["ticket.status.closed"]
            case .all: strings["admin.support.filter_all"]
            }
        }
    }

    static let categories = [
        "SAFETY", "LOST_ITEM", "FARE_DISPUTE", "DRIVER_CONDUCT",
        "PASSENGER_CONDUCT", "VEHICLE_CONDITION", "APP_PROBLEM", "OTHER",
    ]

    private(set) var state: LoadState<SupportQueue> = .loading
    var filter: Filter = .working
    var category: String?
    var onlyUrgent = false
    private var generation = 0

    func ticket(_ id: String) -> AdminTicket? { state.value?.tickets.first { $0.id == id } }

    func apply(deepLink: String?) -> String? {
        guard let deepLink else { return nil }
        let parts = deepLink.split(separator: ":", maxSplits: 1).map(String.init)
        let value = parts.count > 1 ? parts[1] : ""
        switch parts.first?.lowercased() {
        case "working": filter = .working
        case "open": filter = .open
        case "in_progress": filter = .inProgress
        case "resolved": filter = .resolved
        case "closed": filter = .closed
        case "all": filter = .all
        case "urgent": onlyUrgent = true
        case "category": category = value.isEmpty ? nil : value.uppercased()
        case "ticket": return value.isEmpty ? nil : value
        default: break
        }
        return nil
    }

    func load(_ ops: OpsModel) async {
        let mine = generation
        let result = await ops.send(AdminAPI.supportTickets(filter.query, category: category, limit: 200))
        guard mine == generation else { return }
        if case .failure(let error) = result, error == .cancelled { return }
        state = LoadState(result, keeping: state)
    }

    func restart(_ ops: OpsModel) async {
        generation += 1
        state = .loading
        await load(ops)
    }
}

// MARK: - A row

private struct OpTicketRowView: View {
    @Environment(\.strings) private var strings
    let ticket: AdminTicket

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            HStack(spacing: Spacing.s2) {
                // Urgency carries a word, not only a colour.
                if ticket.isUrgent {
                    StatusChip(strings["admin.support.urgent"], tone: .failed)
                }
                Text(OpText.word(ticket.categoryKey, raw: ticket.categoryCode, strings))
                    .opsFont(.heading, weight: .medium)
                    .foregroundStyle(Palette.text)
                    .lineLimit(1)
                Spacer(minLength: 0)
                StatusChip(ticket: ticket.status)
            }
            if let last = ticket.messages.last {
                HStack(spacing: Spacing.s1) {
                    if last.isInternal {
                        Image(systemName: "lock.fill")
                            .foregroundStyle(Palette.attention)
                            .accessibilityLabel(strings["admin.support.internal_note"])
                    }
                    Text(last.body)
                        .lineLimit(2)
                }
                .opsFont(.body)
                .foregroundStyle(Palette.textMuted)
            }
            HStack(spacing: Spacing.s2) {
                LTRText(ticket.reference)
                DotSeparator().accessibilityHidden(true)
                Label(OpsFormat.count(ticket.messages.count, strings), systemImage: "bubble.left.and.bubble.right")
                Spacer(minLength: 0)
                DateText(ticket.createdAt, style: .relative)
            }
            .opsFont(.caption)
            .foregroundStyle(Palette.textMuted)
        }
        .padding(.vertical, Spacing.s1)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("support.row." + ticket.reference)
    }
}

// MARK: - The detail

/// One request, and everything an operator can do about it.
///
/// Internal notes are drawn differently from replies, deliberately and
/// loudly, and sending either is confirmed with who will read it: an operator
/// who writes "this driver has three of these" into the wrong box has sent it
/// to the driver.
struct OpTicketDetailView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    let ticketId: String
    let initial: AdminTicket?
    /// The queue again, after a reply or a decision.
    let onChanged: @MainActor @Sendable () async -> Void

    @State private var model: OpTicketModel?
    @State private var confirm: ConfirmRequest?
    @FocusState private var composing: Bool

    var body: some View {
        Group {
            if let model {
                content(model)
            } else {
                LoadingView()
            }
        }
        .background(Palette.background)
        .opNavigationTitle(model?.ticket.value?.reference ?? initial?.reference ?? "")
        .task(id: ticketId) {
            if model == nil { model = OpTicketModel(ticketId: ticketId, initial: initial) }
        }
        .poll(every: .seconds(30)) { [ops] in
            await model?.load(ops)
        }
        .confirmAction($confirm)
    }

    @ViewBuilder
    private func content(_ model: OpTicketModel) -> some View {
        switch model.ticket {
        case .loading:
            LoadingView()
        case .failed(let error):
            ErrorView(error: error) { [ops] in await model.load(ops) }
        case .loaded(let ticket):
            VStack(spacing: 0) {
                ScrollViewReader { proxy in
                    ScrollView {
                        VStack(alignment: .leading, spacing: Spacing.s4) {
                            header(ticket)
                            ForEach(ticket.messages) { message in
                                OpMessageBubble(message: message).id(message.id)
                            }
                        }
                        .padding(Spacing.s4)
                    }
                    // A long thread opens at its newest message; a short one
                    // stays at the top (a bottom anchor would float it
                    // half-way down an empty pane).
                    .onAppear { scrollToNewest(model, proxy) }
                    // A reply from the reporter (a poll) or one of ours: bring
                    // the newest into view once the layout has settled -- the
                    // sheet that confirmed it may still be leaving.
                    .onChange(of: ticket.messages.count) {
                        scrollToNewest(model, proxy)
                    }
                    // Our own message landed: the keyboard goes, which gives
                    // the thread its height back. Only for a send -- a poll
                    // must never take the keyboard from somebody typing.
                    .onChange(of: model.sent) {
                        composing = false
                        scrollToNewest(model, proxy)
                    }
                }
                Divider()
                composer(ticket, model)
            }
        }
    }

    private func header(_ ticket: AdminTicket) -> some View {
        VStack(alignment: .leading, spacing: Spacing.s3) {
            OpDetailTitle(ticket.reference, subtitle: OpText.word(ticket.categoryKey, raw: ticket.categoryCode, strings),
                          isLatin: true) {
                if ticket.isUrgent { StatusChip(strings["admin.support.urgent"], tone: .failed) }
                StatusChip(ticket.status == .open ? strings["admin.support.filter_open"]
                           : OpText.word(ticket.status.messageKey, raw: ticket.status.rawValue, strings),
                           tone: ticket.status.tone)
            }
            VStack(alignment: .leading, spacing: Spacing.s1) {
                HStack(spacing: Spacing.s2) {
                    Text(strings["admin.col.created"]).foregroundStyle(Palette.textMuted)
                    DateText(ticket.createdAt)
                    DotSeparator().accessibilityHidden(true)
                    DateText(ticket.createdAt, style: .relative).foregroundStyle(Palette.textMuted)
                }
                // Who raised it, from a server that says: his page is a tap away.
                if ticket.reporterId != nil {
                    HStack(spacing: Spacing.s2) {
                        Text(strings["admin.support.reporter"]).foregroundStyle(Palette.textMuted)
                        OpPassengerLink(userId: ticket.reporterId, name: ticket.reporterName)
                        if let phone = ticket.reporterPhone {
                            DotSeparator().accessibilityHidden(true)
                            PhoneLink(phone)
                        }
                    }
                }
                if let trip = ticket.tripId {
                    HStack(spacing: Spacing.s2) {
                        Text(strings["admin.support.about_trip"]).foregroundStyle(Palette.textMuted)
                        LTRText(trip).textSelection(.enabled)
                    }
                }
                if let booking = ticket.bookingId {
                    HStack(spacing: Spacing.s2) {
                        Text(strings["booking.label.number"]).foregroundStyle(Palette.textMuted)
                        LTRText(booking).textSelection(.enabled)
                    }
                }
            }
            .opsFont(.caption)
            if !ticket.nextSteps.isEmpty {
                HStack(spacing: Spacing.s2) {
                    ForEach(ticket.nextSteps, id: \.self) { step in
                        Button(role: step == .closed ? .destructive : nil) {
                            askDecide(ticket, to: step)
                        } label: {
                            Text(stepLabel(step, from: ticket.status))
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                        .disabled(model?.isWorking == true)
                        .accessibilityIdentifier("support.step." + step.rawValue)
                    }
                }
                .opsFont(.label, weight: .medium)
            }
        }
        .opsCard()
    }

    @ViewBuilder
    private func composer(_ ticket: AdminTicket, _ model: OpTicketModel) -> some View {
        @Bindable var model = model
        if ticket.canReply {
            VStack(alignment: .leading, spacing: Spacing.s2) {
                if let error = model.error {
                    Banner(OpText.error(error, strings), tone: .error)
                }
                TextField(strings["admin.support.reply_placeholder"], text: $model.draft, axis: .vertical)
                    .lineLimit(2...6)
                    .textFieldStyle(.roundedBorder)
                    .opsFont(.body)
                    .focused($composing)
                    .accessibilityIdentifier("support.draft")
                HStack(alignment: .top, spacing: Spacing.s3) {
                    Toggle(isOn: $model.isInternal) {
                        VStack(alignment: .leading, spacing: 2) {
                            Label(strings["admin.support.internal_note"], systemImage: "lock")
                                .opsFont(.label, weight: .medium)
                                .foregroundStyle(model.isInternal ? Palette.attention : Palette.text)
                            Text(strings["admin.support.internal_note_hint"])
                                .opsFont(.caption)
                                .foregroundStyle(Palette.textMuted)
                        }
                    }
                    .toggleStyle(.switch)
                    .tint(Palette.attentionEdge)
                    .accessibilityIdentifier("support.internal")
                    Button {
                        askSend(ticket, model)
                    } label: {
                        if model.isWorking {
                            ProgressView().controlSize(.small)
                        } else {
                            Label(strings["admin.support.reply"], systemImage: model.isInternal ? "lock.fill" : "paperplane.fill")
                                // On the accent, its own ink (mint in dark mode); on the
                                // note's amber, white reads.
                                .foregroundStyle(model.isInternal ? Color.white : Palette.onAccent)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(model.isInternal ? Palette.attentionEdge : Palette.accent)
                    .disabled(model.isWorking || model.trimmedDraft.isEmpty)
                    .keyboardShortcut(.return, modifiers: .command)
                    .accessibilityIdentifier("support.send")
                }
            }
            .padding(Spacing.s4)
            .background(model.isInternal ? Palette.bannerWarning : Palette.surface)
        } else {
            Text(strings["error.ticket_closed"])
                .opsFont(.body)
                .foregroundStyle(Palette.textMuted)
                .frame(maxWidth: .infinity)
                .padding(Spacing.s4)
                .background(Palette.surface)
        }
    }

    /// The newest message, in view: after a beat, so a sheet on its way out
    /// and the keyboard going down have finished moving the layout.
    private func scrollToNewest(_ model: OpTicketModel, _ proxy: ScrollViewProxy) {
        Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(350))
            guard let last = model.ticket.value?.messages.last else { return }
            withAnimation { proxy.scrollTo(last.id, anchor: .bottom) }
        }
    }

    /// The panel's words for each move: Start work, Reopen, Mark answered, Close.
    private func stepLabel(_ step: TicketStatus, from current: TicketStatus) -> String {
        switch step {
        case .inProgress: strings[current == .resolved ? "admin.support.reopen" : "admin.support.take"]
        case .resolved: strings["admin.support.resolve"]
        case .closed: strings["admin.support.close"]
        case .open: strings["ticket.status.open"]
        }
    }

    private func askDecide(_ ticket: AdminTicket, to step: TicketStatus) {
        guard let model else { return }
        let label = stepLabel(step, from: ticket.status)
        confirm = ConfirmRequest(
            title: label,
            message: strings["ops.support.status_confirm", [
                "reference": "\u{2066}\(ticket.reference)\u{2069}",
                "status": OpText.word(step.messageKey, raw: step.rawValue, strings),
            ]],
            confirmTitle: label,
            isDestructive: step == .closed
        ) { [ops, onChanged] _ in
            let error = await model.decide(step, ops)
            if error == nil { await onChanged() }
            return error
        }
    }

    private func askSend(_ ticket: AdminTicket, _ model: OpTicketModel) {
        let isInternal = model.isInternal
        let body = model.trimmedDraft
        guard !body.isEmpty else { return }
        confirm = ConfirmRequest(
            title: strings[isInternal ? "admin.support.internal_note" : "admin.support.reply"],
            message: strings[isInternal ? "ops.support.send_note_confirm" : "ops.support.send_reply_confirm"]
                + "\n\n" + body,
            confirmTitle: strings["admin.support.reply"]
        ) { [ops, onChanged] _ in
            let error = await model.send(body: body, isInternal: isInternal, ops)
            if error == nil { await onChanged() }
            return error
        }
    }
}

@MainActor
@Observable
final class OpTicketModel {
    let ticketId: String
    private(set) var ticket: LoadState<AdminTicket>
    var draft = ""
    /// Cleared after every send: left ticked, the next message -- the actual
    /// answer -- went out as a note too, and the person who reported got
    /// silence (Support.tsx).
    var isInternal = false
    private(set) var isWorking = false
    private(set) var error: APIError?
    /// Bumped by every message of ours that lands, for the view to follow.
    private(set) var sent = 0

    init(ticketId: String, initial: AdminTicket?) {
        self.ticketId = ticketId
        self.ticket = initial.map { .loaded($0) } ?? .loading
    }

    var trimmedDraft: String { draft.trimmingCharacters(in: .whitespacesAndNewlines) }

    func load(_ ops: OpsModel) async {
        let result = await ops.send(AdminAPI.ticket(ticketId))
        if case .failure(let failure) = result, failure == .cancelled { return }
        ticket = LoadState(result, keeping: ticket)
    }

    func send(body: String, isInternal: Bool, _ ops: OpsModel) async -> APIError? {
        guard !isWorking else { return nil }
        isWorking = true
        defer { isWorking = false }
        switch await ops.send(AdminAPI.replyToTicket(ticketId, body: body, isInternal: isInternal)) {
        case .success:
            draft = ""
            self.isInternal = false
            error = nil
            await load(ops)
            sent += 1
            return nil
        case .failure(let failure):
            return failure
        }
    }

    func decide(_ status: TicketStatus, _ ops: OpsModel) async -> APIError? {
        guard !isWorking else { return nil }
        isWorking = true
        defer { isWorking = false }
        switch await ops.send(AdminAPI.decideTicket(ticketId, status: status)) {
        case .success:
            await load(ops)
            await ops.refreshAttention()
            return nil
        case .failure(let failure):
            return failure
        }
    }
}

/// A message in the thread. Who wrote it is the reporter or VELRO -- never
/// the author's role, which is a property of the person (Support.tsx) -- and
/// an internal note is framed in amber with a lock and the words.
private struct OpMessageBubble: View {
    @Environment(\.strings) private var strings
    let message: AdminTicketMessage

    private var author: String {
        switch message.isFromReporter {
        case nil: OpText.role(message.authorRole, strings)
        case true?: strings["admin.support.reporter"]
        case false?: strings["admin.support.from_velro"]
        }
    }

    private var fromUs: Bool { message.isFromReporter == false }

    var body: some View {
        HStack {
            if fromUs { Spacer(minLength: Spacing.s12) }
            VStack(alignment: .leading, spacing: Spacing.s1) {
                HStack(spacing: Spacing.s1) {
                    if message.isInternal {
                        Image(systemName: "lock.fill")
                        Text(strings["admin.support.internal_note"]).opsFont(.caption, weight: .bold)
                        DotSeparator()
                    }
                    Text(author)
                    DotSeparator()
                    DateText(message.sentAt)
                }
                .opsFont(.caption)
                .foregroundStyle(message.isInternal ? Palette.onBannerWarning : Palette.textMuted)
                Text(message.body)
                    .opsFont(.body)
                    .foregroundStyle(Palette.text)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(Spacing.s3)
            .background(background, in: RoundedRectangle(cornerRadius: Radius.md, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: Radius.md, style: .continuous)
                    .strokeBorder(message.isInternal ? Palette.attentionEdge : Palette.border,
                                  style: StrokeStyle(lineWidth: message.isInternal ? 1.5 : 1, dash: message.isInternal ? [5, 3] : []))
            }
            if !fromUs { Spacer(minLength: Spacing.s12) }
        }
        .accessibilityElement(children: .combine)
    }

    private var background: Color {
        if message.isInternal { return Palette.bannerWarning }
        return fromUs ? Palette.bannerInfo : Palette.surface
    }
}
