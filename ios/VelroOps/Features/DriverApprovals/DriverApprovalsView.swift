import SwiftUI
import VelroCore

/// Driver approvals, sections 28 and 51 (admin/src/pages/Approvals.tsx).
///
/// A queue: the drivers waiting, longest-waiting first, each row saying how
/// far his papers have got. On iPad and Mac the one selected sits beside the
/// queue; on iPhone he is pushed. Approving or suspending moves to the next.
struct DriverApprovalsView: View {
    @Environment(\.strings) private var strings

    /// The filter that opens this screen on one driver: "driver:<id>".
    static let driverHint = "driver:"

    init() {}

    var body: some View {
        DriverApprovalsScreen()
    }
}

private struct DriverApprovalsScreen: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    #if os(iOS)
    @Environment(\.horizontalSizeClass) private var sizeClass
    #endif
    @State private var queue = DriverQueueModel()

    private var isSplit: Bool {
        #if os(iOS)
        sizeClass != .compact
        #else
        true
        #endif
    }

    var body: some View {
        @Bindable var bindable = queue
        Group {
            if !ops.isOperations {
                EmptyStateView(messageKey: "error.permission_denied", systemImage: "lock")
            } else if isSplit {
                QueueSplit {
                    queueList
                } detail: {
                    detailPane
                }
            } else {
                queueList
                    .navigationDestination(item: $bindable.selection) { id in
                        pushedDetail(id)
                    }
            }
        }
        .background(Palette.background)
        .navigationTitle(strings["admin.approvals.title"])
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                RefreshButton { [queue, ops] in await queue.load(ops) }
            }
        }
        .onAppear {
            queue.autoAdvance = isSplit
            // "pending" (the command centre's card) is this queue as it is;
            // "driver:<id>" ("Review his papers" on a vehicle) opens that driver.
            if let hint = ops.navigator.takeFilter(for: .driverApprovals), hint.hasPrefix(DriverApprovalsView.driverHint) {
                queue.selection = String(hint.dropFirst(DriverApprovalsView.driverHint.count))
            }
        }
        .onChange(of: isSplit) { queue.autoAdvance = isSplit }
        .poll(every: .seconds(60)) { [queue, ops] in
            await queue.load(ops)
        }
    }

    @ViewBuilder private var queueList: some View {
        @Bindable var bindable = queue
        VStack(spacing: 0) {
            if let notice = queue.notice {
                NoticeBanner(notice: notice).padding(Spacing.s3)
            }
            LoadStateView(queue.state, retry: { [queue, ops] in await queue.load(ops) }) { drivers in
                if drivers.isEmpty {
                    EmptyStateView(messageKey: "admin.approvals.none", systemImage: "checkmark.seal")
                } else {
                    List(selection: isSplit ? $bindable.selection : nil) {
                        Section {
                            ForEach(drivers) { driver in
                                row(driver)
                            }
                        } header: {
                            QueueHeader(count: drivers.count, subtitleKey: "admin.approvals.subtitle")
                        }
                    }
                    .listStyle(.plain)
                    .refreshable { [queue, ops] in await queue.load(ops) }
                }
            }
        }
        .animation(.default, value: queue.notice)
    }

    @ViewBuilder private func row(_ driver: AdminDriver) -> some View {
        let content = DriverQueueRow(driver: driver, checklist: queue.checklists[driver.id])
        if isSplit {
            content.tag(driver.id)
        } else {
            Button { queue.selection = driver.id } label: {
                HStack(spacing: Spacing.s2) {
                    content
                    Image(systemName: "chevron.forward")
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(Palette.textMuted)
                        .accessibilityHidden(true)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        }
    }

    @ViewBuilder private var detailPane: some View {
        if let driver = queue.driver(queue.selection) {
            DriverReviewDetail(driver: driver, queue: queue, pushed: false)
                .id(driver.id)
        } else if queue.state.isLoading {
            LoadingView()
        } else {
            EmptyStateView(
                messageKey: queue.drivers.isEmpty ? "admin.approvals.none" : "admin.approvals.select_driver",
                systemImage: "person.text.rectangle"
            )
        }
    }

    /// A pushed destination takes its environment from the NavigationStack,
    /// not from this screen: the words are carried across by hand.
    private func pushedDetail(_ id: String) -> some View {
        Group {
            if let driver = queue.driver(id) {
                DriverReviewDetail(driver: driver, queue: queue, pushed: true)
            } else if queue.state.isLoading {
                LoadingView()
            } else {
                EmptyStateView(messageKey: "admin.approvals.none", systemImage: "checkmark.seal")
            }
        }
        .environment(\.strings, strings)
    }
}

/// The pending drivers and, for each, where his papers stand.
@MainActor
@Observable
final class DriverQueueModel: NoticeShowing {
    private(set) var state: LoadState<[AdminDriver]> = .loading
    /// Each row's checklist, for its progress bar. Fetched together, so a
    /// queue of twenty costs one wait rather than twenty.
    private(set) var checklists: [String: DocumentChecklist] = [:]
    var selection: String?
    /// iPad and Mac: something is always open, and a decision opens the next.
    var autoAdvance = true
    var notice: OpsNotice?

    var drivers: [AdminDriver] { state.value ?? [] }

    func driver(_ id: String?) -> AdminDriver? {
        guard let id else { return nil }
        return drivers.first { $0.id == id }
    }

    func load(_ ops: OpsModel) async {
        let result = await ops.send(AdminAPI.drivers(approvalStatus: .pending, limit: 200))
        if case .failure(let error) = result, error == .cancelled { return }
        // The server lists newest first; a queue serves the longest-waiting first.
        state = LoadState(result.map { Array($0.reversed()) }, keeping: state)
        if autoAdvance, driver(selection) == nil { selection = drivers.first?.id }
        await loadChecklists(ops)
    }

    func refresh(_ driverId: String, ops: OpsModel) async {
        if case .success(let checklist) = await ops.send(AdminAPI.driverDocuments(driverId: driverId)) {
            checklists[driverId] = checklist
        }
    }

    /// Approved or suspended: out of the queue, and on to the next.
    func decided(_ driverId: String, notice: OpsNotice, ops: OpsModel) async {
        let list = drivers
        var next: String?
        if let index = list.firstIndex(where: { $0.id == driverId }) {
            next = (Array(list[(index + 1)...]) + Array(list[..<index])).first?.id
        }
        state = .loaded(list.filter { $0.id != driverId })
        checklists[driverId] = nil
        selection = autoAdvance ? next : nil
        show(notice)
        await load(ops)
        await ops.refreshAttention()
    }

    private func loadChecklists(_ ops: OpsModel) async {
        let ids = drivers.prefix(60).map(\.id)
        let found = await withTaskGroup(of: (String, DocumentChecklist?).self) { group in
            for id in ids {
                group.addTask { (id, try? await ops.send(AdminAPI.driverDocuments(driverId: id)).get()) }
            }
            var out: [String: DocumentChecklist] = [:]
            for await (id, checklist) in group {
                if let checklist { out[id] = checklist }
            }
            return out
        }
        checklists.merge(found) { _, new in new }
    }
}

struct DriverQueueRow: View {
    let driver: AdminDriver
    let checklist: DocumentChecklist?
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            HStack(alignment: .firstTextBaseline, spacing: Spacing.s2) {
                Text(driver.fullName ?? strings["common.value.no_name"])
                    .opsFont(.body, weight: .medium)
                    .foregroundStyle(Palette.text)
                    .lineLimit(1)
                Spacer(minLength: 0)
                if let checklist, checklist.missing.isEmpty {
                    Image(systemName: "checkmark.seal.fill")
                        .foregroundStyle(Palette.accent)
                        .accessibilityLabel(strings["admin.approvals.complete"])
                }
            }
            if let phone = driver.phone {
                LTRText(phone)
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
            }
            if let checklist {
                PaperProgress(slots: checklist.slots)
                if let since = PaperRules.firstUpload(checklist.papers) {
                    HStack(spacing: Spacing.s1) {
                        Text(strings["admin.col.waiting"])
                        DateText(since, style: .relative)
                    }
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
                }
            }
        }
        .padding(.vertical, Spacing.s1)
        .accessibilityElement(children: .combine)
    }
}
