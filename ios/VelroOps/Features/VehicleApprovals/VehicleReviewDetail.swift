import SwiftUI
import VelroCore

/// One car: what it is, whose it is, its papers, and the decision. Activation
/// is refused while its papers are incomplete, so it is offered only when
/// they are not.
struct VehicleReviewDetail: View {
    let queue: VehicleQueueModel
    let pushed: Bool
    @State private var model: VehicleReviewModel
    @State private var viewing: PaperDoc?
    @State private var verifying: PaperDoc?
    @State private var rejecting: PaperDoc?
    @State private var confirm: ConfirmRequest?
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings

    init(vehicle: PendingVehicle, queue: VehicleQueueModel, pushed: Bool) {
        self.queue = queue
        self.pushed = pushed
        _model = State(initialValue: VehicleReviewModel(vehicle: vehicle))
    }

    private var vehicle: PendingVehicle { model.vehicle }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.s4) {
                if let notice = model.notice {
                    NoticeBanner(notice: notice)
                }
                car
                owner
                LoadStateView(model.checklist, retry: { [model, ops] in await model.load(ops) }) { checklist in
                    papers(checklist)
                }
            }
            .padding(Spacing.s4)
            .frame(maxWidth: 880, alignment: .leading)
            .frame(maxWidth: .infinity)
            .animation(.default, value: model.notice)
        }
        .background(Palette.background)
        .modifier(PushedTitle(title: "\u{2066}\(vehicle.plateNumber)\u{2069}", pushed: pushed))
        .refreshable { [model, ops] in await model.load(ops) }
        .task { [model, ops] in await model.load(ops) }
        .paperViewer($viewing, kind: .vehicle, store: model.files, canReview: ops.isOperations, reviewed: reviewed)
        .paperReviewSheets(
            verifying: $verifying, rejecting: $rejecting, kind: .vehicle, store: model.files, reviewed: reviewed
        )
        .confirmAction($confirm)
    }

    private var reviewed: @MainActor (OpsNotice) async -> Void {
        { [model, queue, ops] notice in
            model.show(notice)
            await model.load(ops)
            await queue.refresh(model.vehicle.id, ops: ops)
        }
    }

    // MARK: The car and its owner

    private var car: some View {
        VStack(alignment: .leading, spacing: Spacing.s3) {
            HStack(alignment: .center, spacing: Spacing.s3) {
                Image(systemName: "car.side.fill")
                    .font(.system(size: 28))
                    .foregroundStyle(Palette.accent)
                    .frame(width: 56, height: 56)
                    .background(Palette.bannerInfo, in: RoundedRectangle(cornerRadius: Radius.md, style: .continuous))
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    LTRText(vehicle.plateNumber)
                        .opsFont(.display, weight: .bold)
                        .foregroundStyle(Palette.text)
                    if let description = VehicleText.makeModelYear(
                        brand: vehicle.brand, model: vehicle.model, year: vehicle.year, strings
                    ) {
                        Text(description)
                            .opsFont(.body)
                            .foregroundStyle(Palette.textMuted)
                    }
                }
                Spacer(minLength: 0)
                StatusChip(vehicle: vehicle.status)
            }
            HStack(spacing: Spacing.s4) {
                fact("admin.col.type", strings[VehicleText.typeKey(vehicle.vehicleTypeCode)])
                fact("admin.col.seats", OpsFormat.count(vehicle.seatCapacity, strings))
                if let colour = vehicle.colour, !colour.isEmpty {
                    fact("ops.vehicles.colour", colour)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .opsCard()
    }

    private func fact(_ labelKey: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(strings[labelKey])
                .opsFont(.caption)
                .foregroundStyle(Palette.textMuted)
            Text(value)
                .opsFont(.body, weight: .medium)
                .foregroundStyle(Palette.text)
        }
        .accessibilityElement(children: .combine)
    }

    private var owner: some View {
        VStack(alignment: .leading, spacing: Spacing.s3) {
            Text(strings["admin.vehicles.driver_status"])
                .opsFont(.label)
                .foregroundStyle(Palette.textMuted)
            HStack(alignment: .firstTextBaseline, spacing: Spacing.s2) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(vehicle.driverName ?? strings["common.value.no_name"])
                        .opsFont(.heading)
                        .foregroundStyle(Palette.text)
                    PhoneLink(vehicle.driverPhone)
                        .opsFont(.caption)
                }
                Spacer(minLength: 0)
                StatusChip(driver: vehicle.driverApprovalStatus)
            }
            if vehicle.driverApprovalStatus != .approved {
                Banner(strings["ops.vehicles.driver_not_approved"], tone: .warning, systemImage: "person.badge.clock")
                if vehicle.driverApprovalStatus == .pending {
                    Button {
                        ops.navigator.open(.driverApprovals, filter: DriverApprovalsView.driverHint + vehicle.driverId)
                    } label: {
                        Label(strings["ops.vehicles.open_driver"], systemImage: "person.text.rectangle")
                    }
                    .buttonStyle(.bordered)
                    .opsFont(.label, weight: .medium)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .opsCard()
    }

    // MARK: Papers and the decision

    @ViewBuilder private func papers(_ checklist: VehicleChecklist) -> some View {
        let slots = checklist.slots
        let canReview = ops.isOperations
        VStack(alignment: .leading, spacing: Spacing.s4) {
            SectionHeader("vehicle.documents.title", subtitleKey: "vehicle.documents.subtitle") {
                PaperProgress(slots: slots)
            }
            ForEach(slots) { slot in
                PaperCard(
                    slot: slot, kind: .vehicle, store: model.files, canReview: canReview,
                    open: { viewing = $0 }, verify: { verifying = $0 }, reject: { rejecting = $0 }
                )
            }
            if canReview {
                decision(checklist, slots: slots)
            }
            SupersededPapers(papers: checklist.superseded, kind: .vehicle, store: model.files) { viewing = $0 }
        }
    }

    @ViewBuilder private func decision(_ checklist: VehicleChecklist, slots: [PaperSlot]) -> some View {
        let ready = checklist.missing.isEmpty && slots.allSatisfy { $0.current?.counts == true }
        let isPending = checklist.vehicleStatus == .pending
        VStack(alignment: .leading, spacing: Spacing.s3) {
            if ready {
                Banner(strings["admin.approvals.complete"], tone: .info, systemImage: "checkmark.seal.fill")
            } else {
                Banner(
                    strings["admin.approvals.missing"] + ": " + PaperRules.list(checklist.missing, strings),
                    tone: .warning, systemImage: "exclamationmark.circle"
                )
            }
            HStack(spacing: Spacing.s3) {
                Button(role: .destructive) { confirm = refuseRequest } label: {
                    Label(strings["admin.approvals.reject"], systemImage: "xmark.shield")
                }
                .buttonStyle(.bordered)
                .tint(Palette.danger)
                .disabled(!isPending)
                Spacer(minLength: 0)
                Button { confirm = activateRequest } label: {
                    Label(strings["admin.vehicles.activate"], systemImage: "checkmark.shield")
                }
                .buttonStyle(.borderedProminent)
                .disabled(!ready || !isPending)
            }
            .opsFont(.body, weight: .medium)
            .controlSize(.large)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .opsCard()
    }

    private var activateRequest: ConfirmRequest {
        ConfirmRequest(
            title: strings["admin.vehicles.activate"],
            message: strings["ops.vehicles.activate_confirm", ["plate": "\u{2066}\(vehicle.plateNumber)\u{2069}"]],
            confirmTitle: strings["admin.vehicles.activate"]
        ) { [model, queue, ops, strings] _ in
            await model.decide(approve: true, reason: nil, ops: ops, strings: strings, queue: queue)
        }
    }

    private var refuseRequest: ConfirmRequest {
        ConfirmRequest(
            title: strings["admin.approvals.reject"] + OpsJoin.separator(strings) + "\u{2066}\(vehicle.plateNumber)\u{2069}",
            message: strings["ops.vehicles.reject_reason"],
            confirmTitle: strings["admin.approvals.reject"],
            isDestructive: true,
            reason: .required,
            reasonPrompt: strings["admin.action.reason"]
        ) { [model, queue, ops, strings] reason in
            await model.decide(approve: false, reason: reason, ops: ops, strings: strings, queue: queue)
        }
    }
}

@MainActor
@Observable
final class VehicleReviewModel: NoticeShowing {
    let vehicle: PendingVehicle
    private(set) var checklist: LoadState<VehicleChecklist> = .loading
    var notice: OpsNotice?
    let files = PaperFileStore()

    init(vehicle: PendingVehicle) { self.vehicle = vehicle }

    func load(_ ops: OpsModel) async {
        let result = await ops.send(AdminAPI.vehicleDocuments(vehicleId: vehicle.id))
        if case .failure(let error) = result, error == .cancelled { return }
        checklist = LoadState(result, keeping: checklist)
    }

    func decide(approve: Bool, reason: String?, ops: OpsModel, strings: Strings, queue: VehicleQueueModel) async -> APIError? {
        switch await ops.send(AdminAPI.decideVehicle(vehicle.id, approve: approve, reason: reason)) {
        case .failure(let error):
            if error.code == "VEHICLE_DOCUMENTS_INCOMPLETE" { await load(ops) }
            return error
        case .success(let decision):
            let id = vehicle.id
            let notice = OpsNotice(text: strings[decision.status.messageKey] + OpsJoin.separator(strings) + "\u{2066}\(vehicle.plateNumber)\u{2069}")
            Task {
                try? await Task.sleep(for: .milliseconds(350))
                await queue.decided(id, notice: notice, ops: ops)
            }
            return nil
        }
    }
}
