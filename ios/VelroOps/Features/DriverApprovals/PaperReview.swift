import PDFKit
import SwiftUI
import VelroCore
#if os(iOS)
import UIKit
#elseif os(macOS)
import AppKit
#endif

// The paper review both approval queues share: a driver's papers and a car's
// answer from different endpoints under the same rules (documents.py,
// vehicle_documents.py), so they are reviewed with the same pieces.
//
// Private to Features/DriverApprovals and Features/VehicleApprovals. The
// thumbnail, the viewer and the queue layout are general enough for
// Design/ -- see the report.

// MARK: - Whose paper

enum PaperKind: Sendable, Hashable {
    case driver, vehicle

    func file(_ documentId: String) -> Endpoint<DownloadedFile> {
        switch self {
        case .driver: AdminAPI.documentFile(documentId)
        case .vehicle: AdminAPI.vehicleDocumentFile(documentId)
        }
    }

    /// Verify or reject. Nil on success; the error otherwise, to show where
    /// the operator is looking.
    @MainActor
    func review(
        _ documentId: String, verified: Bool, reason: String? = nil, expiresOn: String? = nil, ops: OpsModel
    ) async -> APIError? {
        switch self {
        case .driver:
            let result = await ops.send(AdminAPI.reviewDocument(
                documentId, verified: verified, rejectionReason: reason, expiresOn: expiresOn
            ))
            if case .failure(let error) = result { return error }
        case .vehicle:
            let result = await ops.send(AdminAPI.reviewVehicleDocument(
                documentId, verified: verified, rejectionReason: reason, expiresOn: expiresOn
            ))
            if case .failure(let error) = result { return error }
        }
        return nil
    }
}

/// A driver's or a car's paper, in one shape.
struct PaperDoc: Identifiable, Hashable, Sendable {
    let id: String
    let typeCode: String
    let status: DocumentStatus
    /// A Kabul day, YYYY-MM-DD: what the driver declared, or the reviewer set.
    let expiresOn: String?
    let rejectionReason: String?
    let uploadedAt: String?
    let isCurrent: Bool

    init(_ document: DriverDocument) {
        id = document.id
        typeCode = document.documentTypeCode
        status = document.status
        expiresOn = document.expiresOn
        rejectionReason = document.rejectionReason
        uploadedAt = document.uploadedAt
        isCurrent = document.isCurrent
    }

    init(_ document: VehicleDocument) {
        id = document.id
        typeCode = document.documentTypeCode
        status = document.status
        expiresOn = document.expiresOn
        rejectionReason = document.rejectionReason
        uploadedAt = document.uploadedAt
        isCurrent = document.isCurrent
    }

    var typeKey: String { PaperRules.typeKey(typeCode) }
    var expiry: DocumentExpiry.Notice? { DocumentExpiry.notice(expiresOn: expiresOn) }
    var isExpired: Bool { expiry?.severity == .past }
    /// What the server counts: verified, and good through its expiry day
    /// (domain/documents.py `is_valid_on`).
    var counts: Bool { status == .verified && !isExpired }
    /// The status to show: a verified paper past its date has stopped counting.
    var shownStatus: DocumentStatus { status == .verified && isExpired ? .expired : status }
    var canVerify: Bool { !counts }
    var canReject: Bool { status != .rejected }
    var uploaded: Date? { ISODate.parse(uploadedAt) }
}

/// A required type, and the paper that stands for it now (nil: never sent).
struct PaperSlot: Identifiable, Hashable, Sendable {
    let typeCode: String
    let current: PaperDoc?
    var id: String { typeCode }
}

enum PaperRules {
    static func typeKey(_ code: String) -> String { "document.type." + code.lowercased() }

    /// A face has no expiry; everything else may.
    static func asksExpiry(_ code: String) -> Bool { code != "SELFIE" }

    /// Papers that always run out: the reviewer is asked for the date rather
    /// than offered it.
    static func needsExpiry(_ code: String) -> Bool { ["LICENSE", "VEHICLE_REGISTRATION"].contains(code) }

    /// Reasons the reviewer gives most, in words the driver can act on.
    static func rejectPresets(_ code: String) -> [String] {
        code == "SELFIE"
            ? ["ops.reject.face_mismatch", "ops.reject.blurry"]
            : ["ops.reject.blurry", "ops.reject.cut_off", "ops.reject.expired", "ops.reject.wrong_document"]
    }

    /// "Driving licence، Photo of your face" -- the separator of the reader's script.
    static func list(_ codes: [String], _ strings: Strings) -> String {
        codes.map { strings[typeKey($0)] }.joined(separator: strings.locale.isRTL ? "، " : ", ")
    }

    static func slots(required: [String], current: (String) -> PaperDoc?) -> [PaperSlot] {
        required.map { PaperSlot(typeCode: $0, current: current($0)) }
    }

    /// When the first paper arrived: the nearest thing to "applied on" the
    /// admin endpoints carry.
    static func firstUpload(_ papers: [PaperDoc]) -> Date? {
        papers.compactMap(\.uploaded).min()
    }
}

extension DocumentChecklist {
    var papers: [PaperDoc] { (documents ?? []).map { PaperDoc($0) } }
    var slots: [PaperSlot] { PaperRules.slots(required: required) { code in current(code).map { PaperDoc($0) } } }
    var superseded: [PaperDoc] { papers.filter { !$0.isCurrent } }
}

extension VehicleChecklist {
    var papers: [PaperDoc] { (documents ?? []).map { PaperDoc($0) } }
    var slots: [PaperSlot] { PaperRules.slots(required: required) { code in current(code).map { PaperDoc($0) } } }
    var superseded: [PaperDoc] { papers.filter { !$0.isCurrent } }
}

// MARK: - A line of news after an action

/// Parts of one line, in the reader's punctuation. A middle dot beside
/// Eastern digits reads as the Persian zero (۰) -- "· ۱" looked like "۱۰" on
/// the payouts tabs -- so Dari and Pashto get the Arabic comma, and a count
/// goes in brackets.
enum OpsJoin {
    static func separator(_ strings: Strings) -> String { strings.locale.isRTL ? "، " : " · " }

    static func counted(_ label: String, _ count: Int, _ strings: Strings) -> String {
        label + " (" + OpsFormat.count(count, strings) + ")"
    }
}

struct OpsNotice: Equatable, Identifiable {
    let id = UUID()
    let text: String
    var isError = false
}

@MainActor
protocol NoticeShowing: AnyObject {
    var notice: OpsNotice? { get set }
}

extension NoticeShowing {
    /// Shown for a few seconds, then gone -- unless another replaced it.
    func show(_ notice: OpsNotice) {
        self.notice = notice
        Task { [weak self] in
            try? await Task.sleep(for: .seconds(5))
            if self?.notice?.id == notice.id { self?.notice = nil }
        }
    }
}

struct NoticeBanner: View {
    let notice: OpsNotice

    var body: some View {
        Banner(
            notice.text,
            tone: notice.isError ? .error : .info,
            systemImage: notice.isError ? "exclamationmark.triangle" : "checkmark.circle"
        )
        .transition(.opacity)
        .onAppear { AccessibilityNotification.Announcement(notice.text).post() }
    }
}

// MARK: - The bytes

#if os(iOS)
typealias PaperImage = UIImage
#elseif os(macOS)
typealias PaperImage = NSImage
#endif

extension Image {
    init(paper: PaperImage) {
        #if os(iOS)
        self.init(uiImage: paper)
        #elseif os(macOS)
        self.init(nsImage: paper)
        #endif
    }
}

/// The files a review screen has fetched, by document id, in memory only
/// and only for as long as the screen that owns it. Keyed by id, so a
/// picture can never be shown under another driver's name.
@MainActor
@Observable
final class PaperFileStore {
    enum Entry {
        case loading
        case image(PaperImage)
        case pdf(Data, thumbnail: PaperImage?)
        /// Downloaded, and it will not decode: a corrupt upload.
        case unreadable
        case failed(APIError)
    }

    private(set) var entries: [String: Entry] = [:]

    func entry(_ id: String) -> Entry? { entries[id] }

    func load(_ id: String, kind: PaperKind, ops: OpsModel) async {
        switch entries[id] {
        case .loading, .image, .pdf, .unreadable: return
        case .failed, .none: break
        }
        entries[id] = .loading
        switch await ops.download(kind.file(id)) {
        case .success(let file):
            entries[id] = Self.decode(file)
        case .failure(let error):
            entries[id] = error == .cancelled ? nil : .failed(error)
        }
    }

    private static func decode(_ file: DownloadedFile) -> Entry {
        if file.isPDF || file.data.starts(with: Data("%PDF".utf8)) {
            guard let document = PDFDocument(data: file.data) else { return .unreadable }
            let thumbnail = document.page(at: 0)?.thumbnail(of: CGSize(width: 480, height: 480), for: .mediaBox)
            return .pdf(file.data, thumbnail: thumbnail)
        }
        guard let image = PaperImage(data: file.data) else { return .unreadable }
        return .image(image)
    }
}

// MARK: - Pieces of a review screen

/// A paper's picture, fetched with the operator's token. Never mirrored: it
/// is a photograph of something physical.
struct PaperThumbnail: View {
    let doc: PaperDoc
    let kind: PaperKind
    let store: PaperFileStore
    var height: CGFloat = 76
    var fill = true
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings

    var body: some View {
        let id = doc.id
        Palette.surfaceMuted
            .overlay { content }
            .frame(height: height)
            .clipShape(RoundedRectangle(cornerRadius: Radius.sm, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: Radius.sm, style: .continuous)
                    .strokeBorder(Palette.border, lineWidth: 1)
            }
            .environment(\.layoutDirection, .leftToRight)
            .task(id: id) { [store, kind, ops] in
                await store.load(id, kind: kind, ops: ops)
            }
    }

    @ViewBuilder private var content: some View {
        switch store.entry(doc.id) {
        case .image(let image):
            Image(paper: image)
                .resizable()
                .aspectRatio(contentMode: fill ? .fill : .fit)
        case .pdf(_, let thumbnail):
            if let thumbnail {
                Image(paper: thumbnail)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .overlay(alignment: .bottomTrailing) {
                        Image(systemName: "doc.richtext")
                            .padding(4)
                            .foregroundStyle(Palette.onAccent)
                            .background(Palette.accent, in: RoundedRectangle(cornerRadius: 4))
                            .padding(4)
                    }
            } else {
                Image(systemName: "doc.richtext").font(.title2).foregroundStyle(Palette.textMuted)
            }
        case .unreadable:
            Image(systemName: "exclamationmark.triangle")
                .font(.title3)
                .foregroundStyle(Palette.danger)
                .accessibilityLabel(strings["admin.approvals.unreadable"])
        case .failed:
            Image(systemName: "icloud.slash")
                .font(.title3)
                .foregroundStyle(Palette.textMuted)
                .accessibilityLabel(strings["admin.approvals.file_unavailable"])
        case .loading, .none:
            ProgressView().controlSize(.small)
        }
    }
}

/// One required paper: its picture, where it stands, and what may be done.
struct PaperCard: View {
    let slot: PaperSlot
    let kind: PaperKind
    let store: PaperFileStore
    let canReview: Bool
    let open: (PaperDoc) -> Void
    let verify: (PaperDoc) -> Void
    let reject: (PaperDoc) -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s3) {
            HStack(alignment: .top, spacing: Spacing.s3) {
                thumbnail
                VStack(alignment: .leading, spacing: Spacing.s1) {
                    Text(strings[PaperRules.typeKey(slot.typeCode)])
                        .opsFont(.heading)
                        .foregroundStyle(Palette.text)
                    if let doc = slot.current {
                        StatusChip(document: doc.shownStatus)
                        details(doc)
                    } else {
                        StatusChip(strings["admin.approvals.not_uploaded"], tone: .failed)
                    }
                }
                Spacer(minLength: 0)
            }
            .accessibilityElement(children: .combine)
            if let doc = slot.current, canReview {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: Spacing.s2) { buttons(doc) }
                    VStack(alignment: .leading, spacing: Spacing.s2) { buttons(doc) }
                }
                .opsFont(.label, weight: .medium)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .opsCard()
    }

    @ViewBuilder private var thumbnail: some View {
        if let doc = slot.current {
            Button { open(doc) } label: {
                PaperThumbnail(doc: doc, kind: kind, store: store, height: 78)
                    .frame(width: 104)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(strings["admin.approvals.view"] + OpsJoin.separator(strings) + strings[doc.typeKey])
        } else {
            RoundedRectangle(cornerRadius: Radius.sm, style: .continuous)
                .strokeBorder(Palette.border, style: StrokeStyle(lineWidth: 1, dash: [4, 3]))
                .frame(width: 104, height: 78)
                .overlay { Image(systemName: "doc").foregroundStyle(Palette.textMuted) }
                .accessibilityHidden(true)
        }
    }

    @ViewBuilder private func details(_ doc: PaperDoc) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: Spacing.s1) {
                Text(strings["admin.approvals.uploaded"])
                DateText(doc.uploadedAt)
            }
            .foregroundStyle(Palette.textMuted)
            if doc.expiresOn != nil {
                HStack(spacing: Spacing.s1) {
                    Text(strings["admin.approvals.expires"])
                    DateText(doc.expiresOn)
                }
                .foregroundStyle(expiryColor(doc))
            }
            if let reason = doc.rejectionReason, !reason.isEmpty {
                Text(reason)
                    .foregroundStyle(Palette.danger)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .opsFont(.caption)
    }

    private func expiryColor(_ doc: PaperDoc) -> Color {
        switch doc.expiry?.severity {
        case .past: Palette.danger
        case .soon: Palette.attention
        default: Palette.textMuted
        }
    }

    @ViewBuilder private func buttons(_ doc: PaperDoc) -> some View {
        Button { open(doc) } label: {
            Label(strings["admin.approvals.view"], systemImage: "eye")
        }
        .buttonStyle(.bordered)
        if doc.canVerify {
            Button { verify(doc) } label: {
                Label(strings["admin.approvals.verify"], systemImage: "checkmark")
            }
            .buttonStyle(.borderedProminent)
        }
        if doc.canReject {
            Button(role: .destructive) { reject(doc) } label: {
                Label(strings["admin.approvals.reject"], systemImage: "xmark")
            }
            .buttonStyle(.bordered)
            // The shell's accent tint outranks the role; a rejection must read red.
            .tint(Palette.danger)
        }
    }
}

/// The face beside the tazkira, the question of whether the person is who
/// he says -- side by side, because comparing from memory is not comparing.
struct IdentityPair: View {
    let selfie: PaperDoc?
    let tazkira: PaperDoc?
    let store: PaperFileStore
    let open: (PaperDoc) -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s3) {
            VStack(alignment: .leading, spacing: 2) {
                Text(strings["admin.approvals.identity"])
                    .opsFont(.heading, weight: .bold)
                    .foregroundStyle(Palette.text)
                    .accessibilityAddTraits(.isHeader)
                Text(strings["admin.approvals.compare"])
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
            }
            HStack(alignment: .top, spacing: Spacing.s3) {
                figure(selfie, captionKey: "document.type.selfie", missingKey: "admin.approvals.no_selfie")
                figure(tazkira, captionKey: "document.type.national_id", missingKey: "admin.approvals.no_tazkira")
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .opsCard()
    }

    @ViewBuilder private func figure(_ doc: PaperDoc?, captionKey: String, missingKey: String) -> some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            Text(strings[captionKey])
                .opsFont(.label)
                .foregroundStyle(Palette.textMuted)
            if let doc {
                Button { open(doc) } label: {
                    PaperThumbnail(doc: doc, kind: .driver, store: store, height: 200, fill: false)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(strings["admin.approvals.view"] + OpsJoin.separator(strings) + strings[captionKey])
            } else {
                Palette.surfaceMuted
                    .frame(height: 200)
                    .overlay {
                        Text(strings[missingKey])
                            .opsFont(.caption)
                            .foregroundStyle(Palette.textMuted)
                            .multilineTextAlignment(.center)
                            .padding(Spacing.s2)
                    }
                    .clipShape(RoundedRectangle(cornerRadius: Radius.sm, style: .continuous))
            }
        }
        .frame(maxWidth: .infinity)
    }
}

/// A row's glance at the papers: one bar per required type, and the count.
struct PaperProgress: View {
    let slots: [PaperSlot]
    @Environment(\.strings) private var strings

    private var verified: Int { slots.filter { $0.current?.counts == true }.count }

    var body: some View {
        let text = strings["ops.approvals.progress", ["verified": verified, "required": slots.count]]
        HStack(spacing: Spacing.s2) {
            HStack(spacing: 3) {
                ForEach(slots) { slot in
                    Capsule().fill(color(slot)).frame(width: 18, height: 6)
                }
            }
            Text(text)
                .opsFont(.caption)
                .foregroundStyle(Palette.textMuted)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(text)
    }

    private func color(_ slot: PaperSlot) -> Color {
        guard let doc = slot.current else { return Palette.border }
        if doc.counts { return Palette.accent }
        return doc.shownStatus == .pending ? Palette.attentionEdge : Palette.danger
    }
}

/// How many wait, above a queue.
struct QueueHeader: View {
    let count: Int
    let subtitleKey: String?
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(strings["ops.queue.waiting", ["count": count]])
                .opsFont(.heading, weight: .bold)
                .foregroundStyle(count > 0 ? Palette.attention : Palette.textMuted)
            if let subtitleKey {
                Text(strings[subtitleKey])
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
            }
        }
        .textCase(nil)
        .padding(.vertical, Spacing.s2)
        .accessibilityAddTraits(.isHeader)
    }
}

/// The queue beside the item being worked on (iPad, Mac). An HStack rather
/// than a second NavigationSplitView: the shell's own split already holds
/// this screen, and splits do not nest.
struct QueueSplit<Queue: View, Detail: View>: View {
    @ViewBuilder var queue: Queue
    @ViewBuilder var detail: Detail

    var body: some View {
        HStack(spacing: 0) {
            queue
                .frame(width: 340)
                .frame(maxHeight: .infinity)
                .background(Palette.surface)
            Divider()
            detail
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }
}

/// Reload, with ⌘R on the Mac and iPad keyboards. One at a time.
struct RefreshButton: View {
    let action: @MainActor @Sendable () async -> Void
    @Environment(\.strings) private var strings
    @State private var isWorking = false

    var body: some View {
        Button {
            Task {
                isWorking = true
                await action()
                isWorking = false
            }
        } label: {
            Label(strings["admin.action.refresh"], systemImage: "arrow.clockwise")
        }
        .disabled(isWorking)
        .keyboardShortcut("r", modifiers: .command)
    }
}

// MARK: - Presenting the review sheets

extension View {
    /// The verify and reject sheets for a paper, wherever it is being looked at.
    func paperReviewSheets(
        verifying: Binding<PaperDoc?>,
        rejecting: Binding<PaperDoc?>,
        kind: PaperKind,
        store: PaperFileStore,
        reviewed: @escaping @MainActor (OpsNotice) async -> Void
    ) -> some View {
        modifier(PaperReviewSheets(
            verifying: verifying, rejecting: rejecting, kind: kind, store: store, reviewed: reviewed
        ))
    }
}

private struct PaperReviewSheets: ViewModifier {
    @Binding var verifying: PaperDoc?
    @Binding var rejecting: PaperDoc?
    let kind: PaperKind
    let store: PaperFileStore
    let reviewed: @MainActor (OpsNotice) async -> Void
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @Environment(\.layoutDirection) private var direction
    @Environment(\.locale) private var locale

    func body(content: Content) -> some View {
        content
            .sheet(item: $verifying) { doc in
                VerifyPaperSheet(doc: doc, kind: kind, store: store, reviewed: reviewed)
                    .carryingOps(ops, strings: strings, direction: direction, locale: locale)
            }
            .sheet(item: $rejecting) { doc in
                RejectPaperSheet(doc: doc, kind: kind, store: store, reviewed: reviewed)
                    .carryingOps(ops, strings: strings, direction: direction, locale: locale)
            }
    }
}

extension View {
    /// A sheet is a new presentation: carry the console, the language and
    /// the direction across.
    func carryingOps(_ ops: OpsModel, strings: Strings, direction: LayoutDirection, locale: Locale) -> some View {
        self
            .environment(ops)
            .environment(\.strings, strings)
            .environment(\.layoutDirection, direction)
            .environment(\.locale, locale)
    }
}
