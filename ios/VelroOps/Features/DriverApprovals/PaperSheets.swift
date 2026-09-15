import SwiftUI
import VelroCore

/// Verify a paper, with its expiry read off the document itself.
///
/// The date goes to the server as a Kabul day (`ISODate.formatDay`), so the
/// picker works in Kabul time and in the reader's calendar -- Hijri Shamsi
/// and Eastern digits for Dari and Pashto. A paper that always runs out asks
/// for the date rather than stamping a default nobody read.
struct VerifyPaperSheet: View {
    let doc: PaperDoc
    let kind: PaperKind
    let store: PaperFileStore
    let reviewed: @MainActor (OpsNotice) async -> Void
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @Environment(\.dismiss) private var dismiss
    @State private var hasExpiry: Bool
    @State private var expiry: Date
    @State private var dateChosen: Bool
    @State private var isWorking = false
    @State private var error: APIError?
    /// The driver declared one at upload: the server keeps it unless it is
    /// replaced, so it can be corrected here but not removed.
    private let declared: Bool

    init(doc: PaperDoc, kind: PaperKind, store: PaperFileStore, reviewed: @escaping @MainActor (OpsNotice) async -> Void) {
        self.doc = doc
        self.kind = kind
        self.store = store
        self.reviewed = reviewed
        let today = Self.today
        let declaredDay = ISODate.parseDay(doc.expiresOn)
        let usable = declaredDay.flatMap { $0 >= today ? $0 : nil }
        declared = declaredDay != nil
        _hasExpiry = State(initialValue: declaredDay != nil || PaperRules.needsExpiry(doc.typeCode))
        _expiry = State(initialValue: usable ?? Self.kabul.date(byAdding: .year, value: 1, to: today) ?? today)
        _dateChosen = State(initialValue: usable != nil)
    }

    private static var kabul: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = Calendars.kabul
        return calendar
    }

    private static var today: Date { kabul.startOfDay(for: .now) }

    private var range: ClosedRange<Date> {
        let today = Self.today
        return today...(Self.kabul.date(byAdding: .year, value: 40, to: today) ?? today)
    }

    private var asks: Bool { PaperRules.asksExpiry(doc.typeCode) }
    private var canVerify: Bool { !isWorking && (!asks || !hasExpiry || dateChosen) }

    private var pickerCalendar: Calendar {
        var calendar = Calendar(identifier: strings.locale == .english ? .gregorian : .persian)
        calendar.timeZone = Calendars.kabul
        calendar.locale = Locale(identifier: strings.locale.tag)
        return calendar
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.s4) {
                PaperSheetHeader(doc: doc, kind: kind, store: store, titleKey: "admin.approvals.verify")
                if asks {
                    Toggle(isOn: $hasExpiry) {
                        Text(strings["ops.approvals.has_expiry"]).opsFont(.body)
                    }
                    .disabled(declared)
                    if hasExpiry {
                        DatePicker(selection: $expiry, in: range, displayedComponents: .date) {
                            Text(strings["admin.col.expires"]).opsFont(.label)
                        }
                        #if os(macOS)
                        .datePickerStyle(.field)
                        #else
                        .datePickerStyle(.graphical)
                        #endif
                        .environment(\.calendar, pickerCalendar)
                        .environment(\.timeZone, Calendars.kabul)
                        .environment(\.locale, Locale(identifier: strings.locale.tag))
                        .onChange(of: expiry) { dateChosen = true }
                        Text(strings[dateChosen ? "ops.approvals.expiry_hint" : "ops.approvals.expiry_needed"])
                            .opsFont(.caption)
                            .foregroundStyle(dateChosen ? Palette.textMuted : Palette.attention)
                    }
                }
                if let error {
                    Banner(strings.forErrorCode(error.code, context: error.context.arguments), tone: .error)
                }
                SheetButtons(
                    confirmTitle: strings["admin.approvals.verify"], isDestructive: false,
                    isWorking: isWorking, canConfirm: canVerify
                ) {
                    Task { await verify() }
                }
            }
            .padding(Spacing.s6)
        }
        .frame(minWidth: 380, idealWidth: 480, maxWidth: 560)
        // The calendar needs the height; a paper without a date does not.
        .presentationDetents(asks && hasExpiry ? [.large] : [.medium, .large])
        .interactiveDismissDisabled(isWorking)
    }

    private func verify() async {
        isWorking = true
        error = nil
        let expires = asks && hasExpiry ? ISODate.formatDay(expiry) : nil
        let failure = await kind.review(doc.id, verified: true, expiresOn: expires, ops: ops)
        if let failure {
            isWorking = false
            if failure != .cancelled { error = failure }
            return
        }
        await reviewed(OpsNotice(text: strings["document.status.verified"] + OpsJoin.separator(strings) + strings[doc.typeKey]))
        isWorking = false
        dismiss()
    }
}

/// Reject a paper. The driver reads the reason, so it is required, and the
/// common ones are a tap away in words he can act on.
struct RejectPaperSheet: View {
    let doc: PaperDoc
    let kind: PaperKind
    let store: PaperFileStore
    let reviewed: @MainActor (OpsNotice) async -> Void
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @Environment(\.dismiss) private var dismiss
    @State private var reason = ""
    @State private var isWorking = false
    @State private var error: APIError?

    private var trimmed: String {
        String(reason.trimmingCharacters(in: .whitespacesAndNewlines).prefix(500))
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.s4) {
                PaperSheetHeader(doc: doc, kind: kind, store: store, titleKey: "admin.approvals.reject_reason")
                VStack(alignment: .leading, spacing: Spacing.s2) {
                    Text(strings["ops.reject.presets"])
                        .opsFont(.label)
                        .foregroundStyle(Palette.textMuted)
                    ForEach(PaperRules.rejectPresets(doc.typeCode), id: \.self) { key in
                        Button { reason = strings[key] } label: {
                            Text(strings[key])
                                .opsFont(.label, weight: .regular)
                                .multilineTextAlignment(.leading)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .buttonStyle(.bordered)
                    }
                }
                VStack(alignment: .leading, spacing: Spacing.s1) {
                    Text(strings["admin.action.reason"])
                        .opsFont(.label)
                        .foregroundStyle(Palette.text)
                    TextField(strings["admin.approvals.reject_reason"], text: $reason, axis: .vertical)
                        .lineLimit(3...6)
                        .textFieldStyle(.roundedBorder)
                        .opsFont(.body)
                    Text(strings["admin.approvals.reject_hint"])
                        .opsFont(.caption)
                        .foregroundStyle(Palette.textMuted)
                }
                if let error {
                    Banner(strings.forErrorCode(error.code, context: error.context.arguments), tone: .error)
                }
                SheetButtons(
                    confirmTitle: strings["admin.approvals.reject"], isDestructive: true,
                    isWorking: isWorking, canConfirm: !isWorking && !trimmed.isEmpty
                ) {
                    Task { await reject() }
                }
            }
            .padding(Spacing.s6)
        }
        .frame(minWidth: 380, idealWidth: 480, maxWidth: 560)
        .presentationDetents([.large])
        .interactiveDismissDisabled(isWorking)
    }

    private func reject() async {
        isWorking = true
        error = nil
        let failure = await kind.review(doc.id, verified: false, reason: trimmed, ops: ops)
        if let failure {
            isWorking = false
            if failure != .cancelled { error = failure }
            return
        }
        await reviewed(OpsNotice(text: strings["document.status.rejected"] + OpsJoin.separator(strings) + strings[doc.typeKey]))
        isWorking = false
        dismiss()
    }
}

/// The paper being decided on, at the top of its sheet.
struct PaperSheetHeader: View {
    let doc: PaperDoc
    let kind: PaperKind
    let store: PaperFileStore
    let titleKey: String
    @Environment(\.strings) private var strings

    var body: some View {
        HStack(alignment: .top, spacing: Spacing.s3) {
            PaperThumbnail(doc: doc, kind: kind, store: store, height: 68)
                .frame(width: 92)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: Spacing.s1) {
                Text(strings[titleKey])
                    .opsFont(.title, weight: .bold)
                    .foregroundStyle(Palette.text)
                Text(strings[doc.typeKey])
                    .opsFont(.body)
                    .foregroundStyle(Palette.textMuted)
            }
            Spacer(minLength: 0)
        }
    }
}

/// Cancel and the decision, at the foot of a sheet; the decision disabled
/// while it is in flight, so one tap is one request.
struct SheetButtons: View {
    let confirmTitle: String
    let isDestructive: Bool
    let isWorking: Bool
    let canConfirm: Bool
    let confirm: () -> Void
    @Environment(\.dismiss) private var dismiss
    @Environment(\.strings) private var strings

    var body: some View {
        HStack(spacing: Spacing.s3) {
            Spacer(minLength: 0)
            Button(strings["common.action.cancel"], role: .cancel) { dismiss() }
                .buttonStyle(.bordered)
                .disabled(isWorking)
            Button(role: isDestructive ? .destructive : nil, action: confirm) {
                if isWorking {
                    ProgressView().controlSize(.small)
                } else {
                    Text(confirmTitle)
                }
            }
            .buttonStyle(.borderedProminent)
            .tint(isDestructive ? Palette.danger : Palette.accent)
            .disabled(!canConfirm)
            .keyboardShortcut(.defaultAction)
        }
        .opsFont(.body, weight: .medium)
    }
}
