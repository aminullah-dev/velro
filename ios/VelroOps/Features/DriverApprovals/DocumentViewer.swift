import PDFKit
import SwiftUI
import VelroCore
#if os(iOS)
import UIKit
#elseif os(macOS)
import AppKit
#endif

/// A paper, full size: pinch or trackpad to zoom, drag to move, double-tap
/// to zoom in or back out, a quarter turn for a photo taken sideways. A PDF
/// opens in PDFKit. The decision is at the foot, so the reviewer decides
/// while looking.
struct DocumentViewer: View {
    let doc: PaperDoc
    let kind: PaperKind
    let store: PaperFileStore
    let canReview: Bool
    let reviewed: @MainActor (OpsNotice) async -> Void
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @Environment(\.dismiss) private var dismiss
    @State private var scale: CGFloat = 1
    @State private var settledScale: CGFloat = 1
    @State private var offset: CGSize = .zero
    @State private var settledOffset: CGSize = .zero
    @State private var quarterTurns = 0
    @State private var verifying: PaperDoc?
    @State private var rejecting: PaperDoc?

    private static let maxScale: CGFloat = 8

    private var decides: Bool { canReview && doc.isCurrent && (doc.canVerify || doc.canReject) }

    var body: some View {
        let id = doc.id
        VStack(spacing: 0) {
            header
            Divider()
            canvas
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            if decides {
                Divider()
                footer
            }
        }
        .background(Palette.background)
        #if os(macOS)
        .frame(minWidth: 720, idealWidth: 920, minHeight: 560, idealHeight: 760)
        #endif
        .task(id: id) { [store, kind, ops] in
            await store.load(id, kind: kind, ops: ops)
        }
        .paperReviewSheets(verifying: $verifying, rejecting: $rejecting, kind: kind, store: store) { [reviewed, dismiss] notice in
            await reviewed(notice)
            dismiss()
        }
    }

    private var header: some View {
        HStack(spacing: Spacing.s3) {
            VStack(alignment: .leading, spacing: 2) {
                Text(strings[doc.typeKey])
                    .opsFont(.heading, weight: .bold)
                    .foregroundStyle(Palette.text)
                HStack(spacing: Spacing.s2) {
                    StatusChip(document: doc.shownStatus)
                    if doc.expiresOn != nil {
                        HStack(spacing: Spacing.s1) {
                            Text(strings["admin.approvals.expires"])
                            DateText(doc.expiresOn)
                        }
                        .opsFont(.caption)
                        .foregroundStyle(doc.isExpired ? Palette.danger : Palette.textMuted)
                    }
                }
            }
            Spacer(minLength: 0)
            Button { dismiss() } label: {
                Label(strings["common.action.close"], systemImage: "xmark")
                    .labelStyle(.iconOnly)
            }
            .buttonStyle(.bordered)
            .keyboardShortcut(.cancelAction)
        }
        .padding(Spacing.s4)
    }

    @ViewBuilder private var canvas: some View {
        let id = doc.id
        switch store.entry(id) {
        case .image(let image):
            zoomable(Image(paper: image))
                .overlay(alignment: .bottom) { zoomControls.padding(Spacing.s3) }
        case .pdf(let data, _):
            PDFKitView(data: data)
                .environment(\.layoutDirection, .leftToRight)
        case .unreadable:
            VStack(spacing: Spacing.s2) {
                Image(systemName: "exclamationmark.triangle")
                    .font(.largeTitle)
                    .foregroundStyle(Palette.danger)
                Text(strings["admin.approvals.unreadable"])
                    .opsFont(.heading, weight: .bold)
                    .foregroundStyle(Palette.text)
                Text(strings["admin.approvals.unreadable_hint"])
                    .opsFont(.body)
                    .foregroundStyle(Palette.textMuted)
            }
            .multilineTextAlignment(.center)
            .padding(Spacing.s6)
        case .failed(let error):
            ErrorView(error: error) { [store, kind, ops] in
                await store.load(id, kind: kind, ops: ops)
            }
        case .loading, .none:
            LoadingView()
        }
    }

    private func zoomable(_ image: Image) -> some View {
        GeometryReader { proxy in
            // A quarter turn swaps the sides: shrink so it still fits.
            let turned = quarterTurns % 2 != 0
            let longest = max(proxy.size.width, proxy.size.height)
            let fit = turned && longest > 0 ? min(proxy.size.width, proxy.size.height) / longest : 1
            image
                .resizable()
                .scaledToFit()
                .frame(width: proxy.size.width, height: proxy.size.height)
                .rotationEffect(.degrees(Double(quarterTurns) * 90))
                .scaleEffect(scale * fit)
                .offset(offset)
                .frame(width: proxy.size.width, height: proxy.size.height)
                .contentShape(Rectangle())
                .gesture(magnify.simultaneously(with: pan))
                .onTapGesture(count: 2) {
                    withAnimation(.snappy) {
                        if scale > 1 { reset() } else { zoom(to: 2.5) }
                    }
                }
        }
        .clipped()
        .background(Color.black)
        // A photograph of a card: never mirrored, and dragged the way the hand moves.
        .environment(\.layoutDirection, .leftToRight)
        .accessibilityElement()
        .accessibilityLabel(strings[doc.typeKey])
        .accessibilityAddTraits(.isImage)
        .accessibilityAction(named: strings["ops.viewer.zoom_in"]) { zoom(by: 1.5) }
        .accessibilityAction(named: strings["ops.viewer.zoom_out"]) { zoom(by: 1 / 1.5) }
        .accessibilityAction(named: strings["ops.viewer.rotate"]) { rotate() }
    }

    private var magnify: some Gesture {
        MagnifyGesture()
            .onChanged { value in
                scale = min(max(settledScale * value.magnification, 1), Self.maxScale)
            }
            .onEnded { _ in
                settledScale = scale
                if scale <= 1.01 { withAnimation(.snappy) { reset() } }
            }
    }

    private var pan: some Gesture {
        DragGesture(minimumDistance: 2)
            .onChanged { value in
                guard scale > 1 else { return }
                offset = CGSize(
                    width: settledOffset.width + value.translation.width,
                    height: settledOffset.height + value.translation.height
                )
            }
            .onEnded { _ in settledOffset = offset }
    }

    private var zoomControls: some View {
        HStack(spacing: Spacing.s1) {
            controlButton("ops.viewer.zoom_out", symbol: "minus.magnifyingglass") { zoom(by: 1 / 1.5) }
                .keyboardShortcut("-", modifiers: .command)
            controlButton("ops.viewer.reset", symbol: "arrow.up.left.and.down.right.magnifyingglass") { reset() }
                .keyboardShortcut("0", modifiers: .command)
            controlButton("ops.viewer.zoom_in", symbol: "plus.magnifyingglass") { zoom(by: 1.5) }
                .keyboardShortcut("=", modifiers: .command)
            controlButton("ops.viewer.rotate", symbol: "rotate.right") { rotate() }
        }
        .padding(Spacing.s1)
        .background(.regularMaterial, in: Capsule())
    }

    private func controlButton(_ key: String, symbol: String, action: @escaping () -> Void) -> some View {
        Button {
            withAnimation(.snappy) { action() }
        } label: {
            Label(strings[key], systemImage: symbol)
                .labelStyle(.iconOnly)
                .font(.system(size: 17, weight: .medium))
                .frame(width: 40, height: 36)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .foregroundStyle(Palette.text)
        .help(strings[key])
    }

    private var footer: some View {
        HStack(spacing: Spacing.s3) {
            Spacer(minLength: 0)
            if doc.canReject {
                Button(role: .destructive) { rejecting = doc } label: {
                    Label(strings["admin.approvals.reject"], systemImage: "xmark")
                }
                .buttonStyle(.bordered)
                .tint(Palette.danger)
            }
            if doc.canVerify {
                Button { verifying = doc } label: {
                    Label(strings["admin.approvals.verify"], systemImage: "checkmark")
                }
                .buttonStyle(.borderedProminent)
            }
        }
        .opsFont(.body, weight: .medium)
        .controlSize(.large)
        .padding(Spacing.s4)
    }

    private func zoom(to value: CGFloat) {
        scale = min(max(value, 1), Self.maxScale)
        settledScale = scale
        if scale == 1 { reset() }
    }

    private func zoom(by factor: CGFloat) { zoom(to: scale * factor) }

    private func reset() {
        scale = 1
        settledScale = 1
        offset = .zero
        settledOffset = .zero
    }

    private func rotate() {
        quarterTurns = (quarterTurns + 1) % 4
        reset()
    }
}

// MARK: - PDFKit, per platform

#if os(iOS)
struct PDFKitView: UIViewRepresentable {
    let data: Data

    func makeUIView(context: Context) -> PDFView {
        let view = PDFView()
        view.autoScales = true
        view.displayMode = .singlePageContinuous
        view.document = PDFDocument(data: data)
        return view
    }

    func updateUIView(_ view: PDFView, context: Context) {}
}
#elseif os(macOS)
struct PDFKitView: NSViewRepresentable {
    let data: Data

    func makeNSView(context: Context) -> PDFView {
        let view = PDFView()
        view.autoScales = true
        view.displayMode = .singlePageContinuous
        view.document = PDFDocument(data: data)
        return view
    }

    func updateNSView(_ view: PDFView, context: Context) {}
}
#endif

// MARK: - Presenting it

extension View {
    /// Full screen on iPhone and iPad; a large sheet on the Mac.
    func paperViewer(
        _ doc: Binding<PaperDoc?>,
        kind: PaperKind,
        store: PaperFileStore,
        canReview: Bool,
        reviewed: @escaping @MainActor (OpsNotice) async -> Void
    ) -> some View {
        modifier(PaperViewerModifier(doc: doc, kind: kind, store: store, canReview: canReview, reviewed: reviewed))
    }
}

private struct PaperViewerModifier: ViewModifier {
    @Binding var doc: PaperDoc?
    let kind: PaperKind
    let store: PaperFileStore
    let canReview: Bool
    let reviewed: @MainActor (OpsNotice) async -> Void
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @Environment(\.layoutDirection) private var direction
    @Environment(\.locale) private var locale

    func body(content: Content) -> some View {
        #if os(iOS)
        content.fullScreenCover(item: $doc) { viewer($0) }
        #else
        content.sheet(item: $doc) { viewer($0) }
        #endif
    }

    private func viewer(_ doc: PaperDoc) -> some View {
        DocumentViewer(doc: doc, kind: kind, store: store, canReview: canReview, reviewed: reviewed)
            .carryingOps(ops, strings: strings, direction: direction, locale: locale)
    }
}
