import Observation
import SwiftUI
import VelroCore

@MainActor
@Observable
final class DocumentsModel {
    private(set) var checklist: DocumentChecklist?
    /// Signed in, not a driver yet: this screen is where he applies.
    private(set) var notADriver = false
    private(set) var isLoading = true
    private(set) var uploadingType: String?
    private(set) var error: APIError?
    var typedName = ""

    private let app: AppModel

    init(app: AppModel) { self.app = app }

    func load() async {
        switch await app.client.send(API.documents()) {
        case .success(let fresh):
            checklist = fresh
            notADriver = false
            error = nil
        case .failure(let failure):
            if failure.code == "DRIVER_NOT_FOUND" || failure.code == "PERMISSION_DENIED" {
                notADriver = true
                checklist = nil
            } else if failure != .cancelled {
                error = failure
            }
        }
        isLoading = false
    }

    func apply() async {
        isLoading = true
        error = nil
        switch await app.client.send(API.registerAsDriver(fullName: typedName)) {
        case .success: await load()
        case .failure(let failure):
            isLoading = false
            if failure != .cancelled { error = failure }
        }
    }

    func upload(_ type: String, _ file: Upload) async {
        guard uploadingType == nil else { return }
        uploadingType = type
        error = nil
        let result = await app.client.send(API.uploadDocument(type: type, file: file))
        uploadingType = nil
        switch result {
        case .success: await load()
        case .failure(let failure):
            if failure.httpStatus == 413 {
                error = APIError(code: "DOCUMENT_TOO_LARGE", httpStatus: 413)
            } else if failure != .cancelled {
                error = failure
            }
        }
    }
}

struct DocumentsView: View {
    @Environment(\.strings) private var strings
    @State private var model: DocumentsModel

    init(app: AppModel) {
        _model = State(initialValue: DocumentsModel(app: app))
    }

    var body: some View {
        VelroScreen(title: strings["driver.documents.title"]) {
            ScrollView {
                VStack(alignment: .leading, spacing: Spacing.md) {
                    if model.isLoading {
                        LoadingState()
                    } else if model.notADriver {
                        apply
                    } else if let checklist = model.checklist {
                        Text(strings[checklist.headlineKey])
                            .velroFont(.body)
                            .foregroundStyle(checklist.canWork ? Palette.primary : Palette.onSurfaceVariant)
                        errorLine
                        ForEach(checklist.required, id: \.self) { type in
                            let current = checklist.current(type)
                            PaperRow(
                                typeCode: type,
                                status: current?.status,
                                uploadedAt: current?.uploadedAt,
                                expiresOn: current?.expiresOn,
                                rejectionReason: current?.rejectionReason,
                                uploading: model.uploadingType == type,
                                enabled: model.uploadingType == nil
                            ) { file in Task { await model.upload(type, file) } }
                        }
                    } else if let error = model.error {
                        ErrorState(error: error) { Task { await model.load() } }
                    }
                }
                .padding(.horizontal, Spacing.gutter)
                .padding(.vertical, Spacing.md)
            }
            .refreshable { await model.load() }
        }
        .task { await model.load() }
    }

    @ViewBuilder
    private var errorLine: some View {
        if let error = model.error {
            if error.code == "DOCUMENT_TOO_LARGE" {
                Text(strings["driver.documents.too_large"])
                    .velroFont(.label)
                    .foregroundStyle(Palette.error)
            } else {
                InlineError(error: error)
            }
        }
    }

    /// Asked here because it is the one moment he is already telling VELRO who
    /// he is. Optional: an operator fills a blank name from the tazkira.
    private var apply: some View {
        VStack(alignment: .leading, spacing: Spacing.md) {
            Text(strings["driver.documents.not_a_driver"])
                .velroFont(.body)
                .foregroundStyle(Palette.onSurface)
            VelroField(label: strings["profile.field.name"], text: $model.typedName, contentType: .name, identifier: "apply.name")
            Text(strings["profile.hint.name_driver"])
                .velroFont(.caption)
                .foregroundStyle(Palette.onSurfaceVariant)
            errorLine
            PrimaryButton(label: strings["driver.documents.apply"]) { Task { await model.apply() } }
                .accessibilityIdentifier("apply.submit")
        }
    }
}
