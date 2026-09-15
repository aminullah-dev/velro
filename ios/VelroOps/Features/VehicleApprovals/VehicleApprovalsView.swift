import SwiftUI
import VelroCore

/// Vehicle activation, section 52 (admin/src/pages/VehicleApprovals.tsx).
///
/// Separate from driver approval because it answers a different question:
/// the driver's papers say the person may drive, these say the car may carry
/// passengers. The owner's own approval is shown beside the car, so an
/// operator can see which half is still missing.
struct VehicleApprovalsView: View {
    @Environment(\.strings) private var strings

    init() {}

    var body: some View {
        VehicleApprovalsScreen()
    }
}

private struct VehicleApprovalsScreen: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    #if os(iOS)
    @Environment(\.horizontalSizeClass) private var sizeClass
    #endif
    @State private var queue = VehicleQueueModel()

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
        .navigationTitle(strings["admin.nav.vehicle_approvals"])
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                RefreshButton { [queue, ops] in await queue.load(ops) }
            }
        }
        .onAppear {
            queue.autoAdvance = isSplit
            // "pending" from the command centre: the pending cars are all this
            // screen lists. "vehicle:<id>" (a driver's or a vehicle's page)
            // opens that car. Taken either way so it does not linger.
            if let hint = ops.navigator.takeFilter(for: .vehicleApprovals), hint.hasPrefix("vehicle:") {
                queue.selection = String(hint.dropFirst("vehicle:".count))
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
            LoadStateView(queue.state, retry: { [queue, ops] in await queue.load(ops) }) { vehicles in
                if vehicles.isEmpty {
                    EmptyStateView(messageKey: "admin.vehicles.none", systemImage: "checkmark.shield")
                } else {
                    List(selection: isSplit ? $bindable.selection : nil) {
                        Section {
                            ForEach(vehicles) { vehicle in
                                row(vehicle)
                            }
                        } header: {
                            QueueHeader(count: vehicles.count, subtitleKey: "admin.vehicles.pending")
                        }
                    }
                    .listStyle(.plain)
                    .refreshable { [queue, ops] in await queue.load(ops) }
                }
            }
        }
        .animation(.default, value: queue.notice)
    }

    @ViewBuilder private func row(_ vehicle: PendingVehicle) -> some View {
        let content = VehicleQueueRow(vehicle: vehicle, checklist: queue.checklists[vehicle.id])
        if isSplit {
            content.tag(vehicle.id)
        } else {
            Button { queue.selection = vehicle.id } label: {
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
        if let vehicle = queue.vehicle(queue.selection) {
            VehicleReviewDetail(vehicle: vehicle, queue: queue, pushed: false)
                .id(vehicle.id)
        } else if queue.state.isLoading {
            LoadingView()
        } else {
            EmptyStateView(
                messageKey: queue.vehicles.isEmpty ? "admin.vehicles.none" : "ops.approvals.select_vehicle",
                systemImage: "car.side"
            )
        }
    }

    /// A pushed destination takes its environment from the NavigationStack,
    /// not from this screen: the words are carried across by hand.
    private func pushedDetail(_ id: String) -> some View {
        Group {
            if let vehicle = queue.vehicle(id) {
                VehicleReviewDetail(vehicle: vehicle, queue: queue, pushed: true)
            } else if queue.state.isLoading {
                LoadingView()
            } else {
                EmptyStateView(messageKey: "admin.vehicles.none", systemImage: "checkmark.shield")
            }
        }
        .environment(\.strings, strings)
    }
}

/// The cars waiting to be activated, oldest first as the server lists them.
@MainActor
@Observable
final class VehicleQueueModel: NoticeShowing {
    private(set) var state: LoadState<[PendingVehicle]> = .loading
    private(set) var checklists: [String: VehicleChecklist] = [:]
    var selection: String?
    var autoAdvance = true
    var notice: OpsNotice?

    var vehicles: [PendingVehicle] { state.value ?? [] }

    func vehicle(_ id: String?) -> PendingVehicle? {
        guard let id else { return nil }
        return vehicles.first { $0.id == id }
    }

    func load(_ ops: OpsModel) async {
        let result = await ops.send(AdminAPI.pendingVehicles(limit: 100))
        if case .failure(let error) = result, error == .cancelled { return }
        state = LoadState(result, keeping: state)
        if autoAdvance, vehicle(selection) == nil { selection = vehicles.first?.id }
        await loadChecklists(ops)
    }

    func refresh(_ vehicleId: String, ops: OpsModel) async {
        if case .success(let checklist) = await ops.send(AdminAPI.vehicleDocuments(vehicleId: vehicleId)) {
            checklists[vehicleId] = checklist
        }
    }

    func decided(_ vehicleId: String, notice: OpsNotice, ops: OpsModel) async {
        let list = vehicles
        var next: String?
        if let index = list.firstIndex(where: { $0.id == vehicleId }) {
            next = (Array(list[(index + 1)...]) + Array(list[..<index])).first?.id
        }
        state = .loaded(list.filter { $0.id != vehicleId })
        checklists[vehicleId] = nil
        selection = autoAdvance ? next : nil
        show(notice)
        await load(ops)
        await ops.refreshAttention()
    }

    private func loadChecklists(_ ops: OpsModel) async {
        let ids = vehicles.prefix(60).map(\.id)
        let found = await withTaskGroup(of: (String, VehicleChecklist?).self) { group in
            for id in ids {
                group.addTask { (id, try? await ops.send(AdminAPI.vehicleDocuments(vehicleId: id)).get()) }
            }
            var out: [String: VehicleChecklist] = [:]
            for await (id, checklist) in group {
                if let checklist { out[id] = checklist }
            }
            return out
        }
        checklists.merge(found) { _, new in new }
    }
}

enum VehicleText {
    /// "Toyota Corolla ۲۰۱۴" -- nil when nothing was given.
    static func makeModelYear(brand: String?, model: String?, year: Int?, _ strings: Strings) -> String? {
        let words = [brand, model].compactMap { $0?.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
            + [year.map { Numerals.format($0, strings.locale) }].compactMap { $0 }
        return words.isEmpty ? nil : words.joined(separator: " ")
    }

    static func typeKey(_ code: String) -> String { "vehicle_type." + code.lowercased() }
}

struct VehicleQueueRow: View {
    let vehicle: PendingVehicle
    let checklist: VehicleChecklist?
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            HStack(alignment: .firstTextBaseline, spacing: Spacing.s2) {
                // Read off a physical car: never mirrored.
                LTRText(vehicle.plateNumber)
                    .opsFont(.heading, weight: .bold)
                    .foregroundStyle(Palette.text)
                StatusChip(
                    key: VehicleText.typeKey(vehicle.vehicleTypeCode), raw: vehicle.vehicleTypeCode, tone: .neutral
                )
                Spacer(minLength: 0)
                if let checklist, checklist.missing.isEmpty {
                    Image(systemName: "checkmark.seal.fill")
                        .foregroundStyle(Palette.accent)
                        .accessibilityLabel(strings["admin.approvals.complete"])
                }
            }
            if let description = VehicleText.makeModelYear(
                brand: vehicle.brand, model: vehicle.model, year: vehicle.year, strings
            ) {
                Text(description)
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
            }
            HStack(spacing: Spacing.s1) {
                Image(systemName: "person")
                    .accessibilityHidden(true)
                Text(vehicle.driverName ?? strings["common.value.no_name"])
                    .lineLimit(1)
                StatusChip(driver: vehicle.driverApprovalStatus)
            }
            .opsFont(.caption)
            .foregroundStyle(Palette.text)
            if let checklist {
                PaperProgress(slots: checklist.slots)
            }
        }
        .padding(.vertical, Spacing.s1)
        .accessibilityElement(children: .combine)
    }
}
