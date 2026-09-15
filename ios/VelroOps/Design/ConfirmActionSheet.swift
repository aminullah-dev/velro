import SwiftUI
import VelroCore

/// An action somebody should confirm before it happens -- approve, reject,
/// suspend, mark paid -- optionally with a reason, which some of the
/// server's refusals require (a rejected paper, a refused payout).
///
///     @State private var confirm: ConfirmRequest?
///     ...
///     confirm = ConfirmRequest(
///         title: strings["admin.approvals.reject"],
///         message: strings["admin.approvals.reject_hint"],
///         confirmTitle: strings["admin.approvals.reject"],
///         isDestructive: true,
///         reason: .required,
///         reasonPrompt: strings["admin.approvals.reject_reason"]
///     ) { [ops] reason in
///         switch await ops.send(AdminAPI.reviewDocument(id, verified: false, rejectionReason: reason)) {
///         case .success: return nil          // closes the sheet
///         case .failure(let error): return error   // shown in the sheet
///         }
///     }
///     ...
///     .confirmAction($confirm)
struct ConfirmRequest: Identifiable {
    enum Reason: Sendable {
        case none, optional, required
    }

    let id = UUID()
    var title: String
    var message: String?
    var confirmTitle: String
    var isDestructive: Bool
    var reason: Reason
    var reasonPrompt: String?
    /// Does the thing. Nil closes the sheet; an error stays in it to read.
    var perform: @MainActor @Sendable (_ reason: String?) async -> APIError?

    init(
        title: String, message: String? = nil, confirmTitle: String, isDestructive: Bool = false,
        reason: Reason = .none, reasonPrompt: String? = nil,
        perform: @escaping @MainActor @Sendable (_ reason: String?) async -> APIError?
    ) {
        self.title = title
        self.message = message
        self.confirmTitle = confirmTitle
        self.isDestructive = isDestructive
        self.reason = reason
        self.reasonPrompt = reasonPrompt
        self.perform = perform
    }
}

struct ConfirmActionSheet: View {
    let request: ConfirmRequest
    @Environment(\.dismiss) private var dismiss
    @Environment(\.strings) private var strings
    @State private var reason = ""
    @State private var isWorking = false
    @State private var error: APIError?

    private var trimmed: String? {
        let text = reason.trimmingCharacters(in: .whitespacesAndNewlines)
        return text.isEmpty ? nil : text
    }

    private var canConfirm: Bool {
        !isWorking && (request.reason != .required || trimmed != nil)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s4) {
            Text(request.title)
                .opsFont(.title, weight: .bold)
                .foregroundStyle(Palette.text)
            if let message = request.message {
                Text(message)
                    .opsFont(.body)
                    .foregroundStyle(Palette.textMuted)
            }
            if request.reason != .none {
                VStack(alignment: .leading, spacing: Spacing.s1) {
                    Text(strings["admin.action.reason"])
                        .opsFont(.label)
                        .foregroundStyle(Palette.text)
                    TextField(request.reasonPrompt ?? "", text: $reason, axis: .vertical)
                        .lineLimit(3...6)
                        .textFieldStyle(.roundedBorder)
                        .opsFont(.body)
                }
            }
            if let error {
                Banner(strings.forErrorCode(error.code, context: error.context.arguments), tone: .error)
            }
            HStack(spacing: Spacing.s3) {
                Spacer(minLength: 0)
                Button(strings["common.action.cancel"], role: .cancel) { dismiss() }
                    .buttonStyle(.bordered)
                    .disabled(isWorking)
                Button(role: request.isDestructive ? .destructive : nil) {
                    Task { await confirm() }
                } label: {
                    if isWorking {
                        ProgressView().controlSize(.small)
                    } else {
                        Text(request.confirmTitle)
                    }
                }
                .buttonStyle(.borderedProminent)
                // The app's green tint outranks `role: .destructive`; a
                // reject or a suspend must not wear the colour of approve.
                // The deep red and the accent's own ink read in both themes
                // (white on the dark theme's mint or pink does not).
                .tint(request.isDestructive ? Palette.red700 : Palette.accent)
                .foregroundStyle(request.isDestructive ? Color.white : Palette.onAccent)
                .disabled(!canConfirm)
                .keyboardShortcut(.defaultAction)
            }
        }
        .padding(Spacing.s6)
        .frame(minWidth: 320, idealWidth: 440, maxWidth: 560, alignment: .leading)
        .presentationDetents([.medium, .large])
        .interactiveDismissDisabled(isWorking)
    }

    private func confirm() async {
        isWorking = true
        error = nil
        let failure = await request.perform(request.reason == .none ? nil : trimmed)
        isWorking = false
        if let failure {
            if failure != .cancelled { error = failure }
        } else {
            dismiss()
        }
    }
}

private struct ConfirmActionModifier: ViewModifier {
    @Binding var request: ConfirmRequest?
    @Environment(\.strings) private var strings
    @Environment(\.layoutDirection) private var direction

    func body(content: Content) -> some View {
        content.sheet(item: $request) { request in
            ConfirmActionSheet(request: request)
                // A sheet is a new presentation: carry the language across.
                .environment(\.strings, strings)
                .environment(\.layoutDirection, direction)
        }
    }
}

extension View {
    /// Presents the sheet whenever `request` is set, and clears it on close.
    func confirmAction(_ request: Binding<ConfirmRequest?>) -> some View {
        modifier(ConfirmActionModifier(request: request))
    }
}
