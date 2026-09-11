import PhotosUI
import SwiftUI
import UIKit
import VelroCore

/// One paper he owes VELRO: what it is, where it stands, and a way to send a
/// photograph of it. The same row for his own papers and his car's.
struct PaperRow: View {
    let typeCode: String
    let status: DocumentStatus?
    let uploadedAt: String?
    let expiresOn: String?
    let rejectionReason: String?
    let uploading: Bool
    let enabled: Bool
    let send: (Upload) -> Void

    @Environment(\.strings) private var strings
    @State private var choosing = false
    @State private var camera = false
    @State private var library = false
    @State private var picked: PhotosPickerItem?

    /// The selfie is taken there and then with the camera, so it can be
    /// matched to the tazkira -- not an old picture from the gallery.
    private var cameraOnly: Bool { typeCode == "SELFIE" }

    var body: some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.sm) {
                HStack(alignment: .firstTextBaseline) {
                    Text(strings["document.type.\(typeCode.lowercased())"])
                        .velroFont(.heading, weight: .medium)
                        .foregroundStyle(Palette.onSurface)
                    Spacer()
                    if let status {
                        StatusChip(key: "document.status.\(status.rawValue.lowercased())", tone: tone(status))
                    }
                }
                if cameraOnly {
                    Text(strings["document.selfie.hint"])
                        .velroFont(.caption)
                        .foregroundStyle(Palette.onSurfaceVariant)
                }
                if let sent = ISODate.parse(uploadedAt) {
                    Text(strings["driver.documents.sent_on", ["date": Calendars.date(sent, strings.locale)]])
                        .velroFont(.caption)
                        .foregroundStyle(Palette.onSurfaceVariant)
                } else if status == nil {
                    Text(strings["driver.documents.not_sent"])
                        .velroFont(.caption)
                        .foregroundStyle(Palette.accent)
                }
                if let notice = DocumentExpiry.notice(expiresOn: expiresOn) {
                    Text(strings[notice.messageKey, ["date": Calendars.date(notice.date, strings.locale)]])
                        .velroFont(.caption, weight: notice.severity == .fine ? nil : .medium)
                        .foregroundStyle(notice.severity == .fine ? Palette.onSurfaceVariant : Palette.error)
                }
                if status == .rejected, let reason = rejectionReason, !reason.isEmpty {
                    Text(reason)
                        .velroFont(.label)
                        .foregroundStyle(Palette.error)
                }
                SecondaryButton(
                    label: strings[status == nil ? "driver.documents.send" : "driver.documents.replace"],
                    enabled: enabled && !uploading
                ) { choose() }
                .overlay { if uploading { ProgressView() } }
                .accessibilityIdentifier("paper.\(typeCode)")
            }
        }
        .confirmationDialog(strings["document.type.\(typeCode.lowercased())"], isPresented: $choosing) {
            Button(strings["document.source.camera"]) { camera = true }
            Button(strings["document.source.library"]) { library = true }
            Button(strings["common.action.cancel"], role: .cancel) {}
        }
        .fullScreenCover(isPresented: $camera) {
            CameraPicker(front: cameraOnly) { image in
                camera = false
                if let image, let data = PhotoUpload.jpeg(image) { send(.jpeg(data, name: "\(typeCode.lowercased()).jpg")) }
            }
            .ignoresSafeArea()
        }
        .photosPicker(isPresented: $library, selection: $picked, matching: .images)
        .onChange(of: picked) { _, item in
            guard let item else { return }
            picked = nil
            Task {
                guard let data = try? await item.loadTransferable(type: Data.self),
                      let image = UIImage(data: data),
                      let jpeg = PhotoUpload.jpeg(image) else { return }
                send(.jpeg(jpeg, name: "\(typeCode.lowercased()).jpg"))
            }
        }
    }

    private func choose() {
        let hasCamera = UIImagePickerController.isSourceTypeAvailable(.camera)
        if cameraOnly && hasCamera {
            camera = true
        } else if hasCamera {
            choosing = true
        } else {
            // No camera (a simulator, a broken one): the library is the only way.
            library = true
        }
    }

    private func tone(_ status: DocumentStatus) -> StatusTone {
        switch status {
        case .pending: .attention
        case .verified: .active
        case .rejected, .expired: .failed
        }
    }
}

/// A photograph made small enough to send over a village's mobile data and
/// under the server's six-megabyte limit, without losing the print on a
/// licence: 2000 pixels on the long side is more than a tazkira needs.
enum PhotoUpload {
    static let maxBytes = 5_500_000

    static func jpeg(_ image: UIImage, longEdge: CGFloat = 2000) -> Data? {
        let scale = min(1, longEdge / max(image.size.width, image.size.height))
        let size = CGSize(width: (image.size.width * scale).rounded(), height: (image.size.height * scale).rounded())
        let format = UIGraphicsImageRendererFormat.default()
        format.scale = 1
        let drawn = UIGraphicsImageRenderer(size: size, format: format).image { _ in
            image.draw(in: CGRect(origin: .zero, size: size))
        }
        for quality in [0.8, 0.65, 0.5, 0.35] {
            if let data = drawn.jpegData(compressionQuality: quality), data.count <= maxBytes { return data }
        }
        return nil
    }
}

/// The camera, for a paper photographed there and then.
struct CameraPicker: UIViewControllerRepresentable {
    var front = false
    let done: (UIImage?) -> Void

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        if front, UIImagePickerController.isCameraDeviceAvailable(.front) { picker.cameraDevice = .front }
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ controller: UIImagePickerController, context: Context) {}

    func makeCoordinator() -> Coordinator { Coordinator(done: done) }

    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let done: (UIImage?) -> Void
        init(done: @escaping (UIImage?) -> Void) { self.done = done }

        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            done(info[.originalImage] as? UIImage)
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { done(nil) }
    }
}
