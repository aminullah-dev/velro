import SwiftUI
import VelroCore

/// One applicant: who he is, the face beside the tazkira, every required
/// paper and the decision. Approval is enabled only when every required paper
/// is verified and in date -- the server's own rule (domain/driver.py) -- and
/// carries the name as it reads on the tazkira, which the operator may correct.
struct DriverReviewDetail: View {
    let queue: DriverQueueModel
    let pushed: Bool
    @State private var model: DriverReviewModel
    @State private var viewing: PaperDoc?
    @State private var verifying: PaperDoc?
    @State private var rejecting: PaperDoc?
    @State private var confirm: ConfirmRequest?
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings

    init(driver: AdminDriver, queue: DriverQueueModel, pushed: Bool) {
        self.queue = queue
        self.pushed = pushed
        _model = State(initialValue: DriverReviewModel(driver: driver))
    }

    private var displayName: String { model.driver.fullName ?? strings["common.value.no_name"] }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.s4) {
                if let notice = model.notice {
                    NoticeBanner(notice: notice)
                }
                profile
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
        .modifier(PushedTitle(title: displayName, pushed: pushed))
        .refreshable { [model, ops] in await model.load(ops) }
        .task { [model, ops] in await model.load(ops) }
        .paperViewer($viewing, kind: .driver, store: model.files, canReview: ops.isOperations, reviewed: reviewed)
        .paperReviewSheets(
            verifying: $verifying, rejecting: $rejecting, kind: .driver, store: model.files, reviewed: reviewed
        )
        .confirmAction($confirm)
    }

    /// After a paper is verified or rejected: say so, and read both lists again.
    private var reviewed: @MainActor (OpsNotice) async -> Void {
        { [model, queue, ops] notice in
            model.show(notice)
            await model.load(ops)
            await queue.refresh(model.driver.id, ops: ops)
        }
    }

    // MARK: Who

    private var profile: some View {
        HStack(alignment: .top, spacing: Spacing.s4) {
            avatar
            VStack(alignment: .leading, spacing: Spacing.s1) {
                Text(displayName)
                    .opsFont(.title, weight: .bold)
                    .foregroundStyle(Palette.text)
                PhoneLink(model.driver.phone)
                    .opsFont(.body)
                HStack(spacing: Spacing.s2) {
                    StatusChip(driver: model.driver.approvalStatus)
                    if let plate = model.driver.plateNumber {
                        // His car, by plate; its own approval is on the vehicle screen.
                        HStack(spacing: Spacing.s1) {
                            Image(systemName: "car.side")
                                .accessibilityHidden(true)
                            LTRText(plate)
                                .lineLimit(1)
                        }
                        .opsFont(.caption, weight: .medium)
                        .foregroundStyle(Palette.text)
                        .fixedSize()
                        .padding(.horizontal, Spacing.s3)
                        .padding(.vertical, 3)
                        .background(Palette.surfaceMuted, in: Capsule())
                    }
                }
                if let since = PaperRules.firstUpload(model.checklist.value?.papers ?? []) {
                    HStack(spacing: Spacing.s1) {
                        Text(strings["admin.col.waiting"])
                        DateText(since, style: .dateTime)
                    }
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
                }
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .opsCard()
    }

    @ViewBuilder private var avatar: some View {
        if let selfie = model.checklist.value?.current("SELFIE").map({ PaperDoc($0) }) {
            PaperThumbnail(doc: selfie, kind: .driver, store: model.files, height: 72)
                .frame(width: 72)
                .clipShape(Circle())
                .accessibilityHidden(true)
        } else {
            Circle()
                .fill(Palette.surfaceMuted)
                .frame(width: 72, height: 72)
                .overlay {
                    Image(systemName: "person.fill")
                        .font(.title)
                        .foregroundStyle(Palette.textMuted)
                }
                .accessibilityHidden(true)
        }
    }

    // MARK: The papers

    @ViewBuilder private func papers(_ checklist: DocumentChecklist) -> some View {
        let slots = checklist.slots
        let canReview = ops.isOperations
        VStack(alignment: .leading, spacing: Spacing.s4) {
            if checklist.required.contains("SELFIE") || checklist.required.contains("NATIONAL_ID") {
                IdentityPair(
                    selfie: checklist.current("SELFIE").map { PaperDoc($0) },
                    tazkira: checklist.current("NATIONAL_ID").map { PaperDoc($0) },
                    store: model.files
                ) { viewing = $0 }
            }
            SectionHeader("admin.approvals.documents") {
                PaperProgress(slots: slots)
            }
            ForEach(slots) { slot in
                PaperCard(
                    slot: slot, kind: .driver, store: model.files, canReview: canReview,
                    open: { viewing = $0 }, verify: { verifying = $0 }, reject: { rejecting = $0 }
                )
            }
            if canReview {
                decision(checklist, slots: slots)
            }
            SupersededPapers(papers: checklist.superseded, kind: .driver, store: model.files) { viewing = $0 }
        }
    }

    // MARK: The decision

    @ViewBuilder private func decision(_ checklist: DocumentChecklist, slots: [PaperSlot]) -> some View {
        @Bindable var editing = model
        let ready = checklist.missing.isEmpty && slots.allSatisfy { $0.current?.counts == true }
        let isPending = checklist.approvalStatus == .pending
        VStack(alignment: .leading, spacing: Spacing.s3) {
            if ready {
                Banner(strings["admin.approvals.complete"], tone: .info, systemImage: "checkmark.seal.fill")
            } else {
                Banner(
                    strings["admin.approvals.missing"] + ": " + PaperRules.list(checklist.missing, strings),
                    tone: .warning, systemImage: "exclamationmark.circle"
                )
            }
            VStack(alignment: .leading, spacing: Spacing.s1) {
                Text(strings["admin.approvals.record_name"])
                    .opsFont(.label)
                    .foregroundStyle(Palette.text)
                TextField(strings["ops.approvals.name_placeholder"], text: $editing.name)
                    .textFieldStyle(.roundedBorder)
                    .opsFont(.body)
                    #if os(iOS)
                    .textContentType(.name)
                    #endif
                Text(strings["admin.approvals.name_hint"])
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
            }
            .disabled(!isPending)
            HStack(spacing: Spacing.s3) {
                Button(role: .destructive) { confirm = suspendRequest } label: {
                    Label(strings["admin.action.suspend"], systemImage: "hand.raised")
                }
                .buttonStyle(.bordered)
                .tint(Palette.danger)
                Spacer(minLength: 0)
                Button { confirm = approveRequest } label: {
                    Label(strings["admin.approvals.approve_driver"], systemImage: "checkmark.seal")
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

    private var approveRequest: ConfirmRequest {
        let typed = model.name.trimmingCharacters(in: .whitespacesAndNewlines)
        let name = typed.isEmpty ? displayName : typed
        return ConfirmRequest(
            title: strings["admin.approvals.approve_driver"],
            message: strings["ops.approvals.approve_confirm", ["name": name]],
            confirmTitle: strings["admin.approvals.approve_driver"]
        ) { [model, queue, ops, strings] _ in
            await model.approve(ops: ops, strings: strings, queue: queue)
        }
    }

    private var suspendRequest: ConfirmRequest {
        ConfirmRequest(
            title: strings["admin.action.suspend"] + OpsJoin.separator(strings) + displayName,
            message: strings["ops.approvals.suspend_hint"],
            confirmTitle: strings["admin.action.suspend"],
            isDestructive: true,
            reason: .required,
            reasonPrompt: strings["admin.action.reason"]
        ) { [model, queue, ops, strings] reason in
            await model.suspend(reason: reason, ops: ops, strings: strings, queue: queue)
        }
    }
}

@MainActor
@Observable
final class DriverReviewModel: NoticeShowing {
    let driver: AdminDriver
    private(set) var checklist: LoadState<DocumentChecklist> = .loading
    /// The name as it reads on the tazkira, prefilled from the application.
    var name: String
    var notice: OpsNotice?
    /// This driver's pictures, gone with this screen.
    let files = PaperFileStore()

    init(driver: AdminDriver) {
        self.driver = driver
        name = driver.fullName ?? ""
    }

    func load(_ ops: OpsModel) async {
        let result = await ops.send(AdminAPI.driverDocuments(driverId: driver.id))
        if case .failure(let error) = result, error == .cancelled { return }
        checklist = LoadState(result, keeping: checklist)
    }

    func approve(ops: OpsModel, strings: Strings, queue: DriverQueueModel) async -> APIError? {
        let typed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        switch await ops.send(AdminAPI.approveDriver(driver.id, fullName: typed.isEmpty ? nil : typed)) {
        case .failure(let error):
            // Refused as incomplete: the checklist on screen is out of date.
            if error.code == "DRIVER_DOCUMENTS_INCOMPLETE" { await load(ops) }
            return error
        case .success:
            let shown = typed.isEmpty ? (driver.fullName ?? strings["common.value.no_name"]) : typed
            leave(queue, ops: ops, notice: OpsNotice(text: strings["driver.approval.approved"] + OpsJoin.separator(strings) + shown))
            return nil
        }
    }

    func suspend(reason: String?, ops: OpsModel, strings: Strings, queue: DriverQueueModel) async -> APIError? {
        switch await ops.send(AdminAPI.suspendDriver(driver.id, reason: reason)) {
        case .failure(let error):
            return error
        case .success:
            let shown = driver.fullName ?? strings["common.value.no_name"]
            leave(queue, ops: ops, notice: OpsNotice(text: strings["driver.approval.suspended"] + OpsJoin.separator(strings) + shown))
            return nil
        }
    }

    /// Once the confirmation sheet has closed, hand back to the queue.
    private func leave(_ queue: DriverQueueModel, ops: OpsModel, notice: OpsNotice) {
        let id = driver.id
        Task {
            try? await Task.sleep(for: .milliseconds(350))
            await queue.decided(id, notice: notice, ops: ops)
        }
    }
}

/// Uploads a newer one replaced, so a reviewer can see what was sent before.
struct SupersededPapers: View {
    let papers: [PaperDoc]
    let kind: PaperKind
    let store: PaperFileStore
    let open: (PaperDoc) -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        if !papers.isEmpty {
            DisclosureGroup {
                VStack(spacing: Spacing.s2) {
                    ForEach(papers) { doc in
                        Button { open(doc) } label: {
                            HStack(spacing: Spacing.s3) {
                                PaperThumbnail(doc: doc, kind: kind, store: store, height: 44)
                                    .frame(width: 60)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(strings[doc.typeKey])
                                        .opsFont(.label)
                                        .foregroundStyle(Palette.text)
                                    DateText(doc.uploadedAt)
                                        .opsFont(.caption)
                                        .foregroundStyle(Palette.textMuted)
                                }
                                Spacer(minLength: 0)
                                StatusChip(document: doc.status)
                            }
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityElement(children: .combine)
                    }
                }
                .padding(.top, Spacing.s2)
            } label: {
                HStack(spacing: Spacing.s2) {
                    Text(strings["admin.approvals.superseded"])
                        .opsFont(.label)
                        .foregroundStyle(Palette.text)
                    StatusChip(OpsFormat.count(papers.count, strings))
                }
            }
            .opsCard()
        }
    }
}

/// A pushed detail names itself; beside the queue, the screen's title stays.
struct PushedTitle: ViewModifier {
    let title: String
    let pushed: Bool

    func body(content: Content) -> some View {
        if pushed {
            content
                .navigationTitle(title)
                #if os(iOS)
                .navigationBarTitleDisplayMode(.inline)
                #endif
        } else {
            content
        }
    }
}
