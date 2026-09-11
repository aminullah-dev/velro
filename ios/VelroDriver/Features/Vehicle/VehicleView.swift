import Observation
import SwiftUI
import VelroCore

@MainActor
@Observable
final class VehicleModel {
    private(set) var vehicle: DriverVehicle?
    private(set) var papers: VehicleChecklist?
    private(set) var types: [VehicleType] = []
    private(set) var isLoading = true
    private(set) var isSaving = false
    private(set) var uploadingPaper: String?
    private(set) var error: APIError?
    var isEditing = false

    var typeCode = "" {
        didSet {
            // The type's usual seat count, unless he has already typed his own.
            let previous = types.first { $0.code == oldValue }?.defaultSeatCapacity
            if seats.isEmpty || Int(seats) == previous,
               let usual = types.first(where: { $0.code == typeCode })?.defaultSeatCapacity {
                seats = String(usual)
            }
        }
    }
    var plate = ""
    var seats = ""
    var brand = ""
    var model = ""
    var year = ""
    var colour = ""

    private let app: AppModel

    init(app: AppModel) { self.app = app }

    var canSubmit: Bool {
        !isSaving && !typeCode.isEmpty && plate.trimmingCharacters(in: .whitespaces).count >= 2
            && (seats.isEmpty || (Int(seats).map { (1...60).contains($0) } ?? false))
            && (year.isEmpty || (Int(year).map { (1950...2100).contains($0) } ?? false))
    }

    func load() async {
        error = nil
        guard case .success(let fetchedTypes) = await app.client.send(API.vehicleTypes()) else {
            isLoading = false
            error = .offline
            return
        }
        types = fetchedTypes
        switch await app.client.sendNullable(API.currentVehicle()) {
        case .success(let current):
            vehicle = current
            if let current, case .success(let checklist) = await app.client.send(API.vehicleDocuments(vehicleId: current.id)) {
                papers = checklist
            }
            fill(from: current)
            // No car yet: the form is the screen.
            isEditing = current == nil
        case .failure(let failure):
            if failure != .cancelled { error = failure }
        }
        isLoading = false
    }

    func fill(from vehicle: DriverVehicle?) {
        typeCode = vehicle?.vehicleTypeCode ?? (types.first?.code ?? "")
        plate = vehicle?.plateNumber ?? ""
        seats = vehicle.map { String($0.seatCapacity) } ?? seats
        brand = vehicle?.brand ?? ""
        model = vehicle?.model ?? ""
        year = vehicle?.year.map(String.init) ?? ""
        colour = vehicle?.colour ?? ""
    }

    func submit() async {
        guard canSubmit else { return }
        isSaving = true
        error = nil
        let result = await app.client.send(API.registerVehicle(
            typeCode: typeCode, plate: plate, seats: Int(seats), brand: brand, model: model, year: Int(year), colour: colour
        ))
        isSaving = false
        switch result {
        case .success:
            isEditing = false
            await load()
        case .failure(let failure):
            if failure != .cancelled { error = failure }
        }
    }

    func uploadPaper(_ type: String, _ file: Upload) async {
        guard let vehicle, uploadingPaper == nil else { return }
        uploadingPaper = type
        error = nil
        let result = await app.client.send(API.uploadVehicleDocument(vehicleId: vehicle.id, type: type, file: file))
        uploadingPaper = nil
        switch result {
        case .success:
            if case .success(let checklist) = await app.client.send(API.vehicleDocuments(vehicleId: vehicle.id)) { papers = checklist }
        case .failure(let failure):
            if failure != .cancelled { error = failure }
        }
    }
}

struct VehicleView: View {
    @Environment(\.strings) private var strings
    @State private var model: VehicleModel

    init(app: AppModel) {
        _model = State(initialValue: VehicleModel(app: app))
    }

    var body: some View {
        VelroScreen(title: strings["driver.vehicle.title"]) {
            ScrollView {
                VStack(alignment: .leading, spacing: Spacing.md) {
                    if model.isLoading {
                        LoadingState()
                    } else if model.isEditing {
                        form
                    } else if let vehicle = model.vehicle {
                        summary(vehicle)
                        papers
                    } else if let error = model.error {
                        ErrorState(error: error) { Task { await model.load() } }
                    }
                }
                .padding(.horizontal, Spacing.gutter)
                .padding(.vertical, Spacing.md)
            }
        }
        .task { await model.load() }
    }

    private func summary(_ vehicle: DriverVehicle) -> some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.sm) {
                HStack {
                    Text(vehicle.makeAndModel ?? strings[model.types.first { $0.code == vehicle.vehicleTypeCode }?.nameKey ?? "common.value.unknown"])
                        .velroFont(.heading, weight: .medium)
                        .foregroundStyle(Palette.onSurface)
                    Spacer()
                    PlateText(plate: vehicle.plateNumber)
                }
                Text(strings["driver.vehicle.seats_count", ["count": vehicle.seatCapacity]])
                    .velroFont(.label)
                    .foregroundStyle(Palette.onSurfaceVariant)
                Text(strings[statusKey(vehicle.status)])
                    .velroFont(.label, weight: .medium)
                    .foregroundStyle(vehicle.status == .active ? Palette.primary : Palette.accent)
                if let error = model.error { InlineError(error: error) }
                SecondaryButton(label: strings["driver.vehicle.edit"]) { model.isEditing = true }
                    .accessibilityIdentifier("vehicle.edit")
            }
        }
    }

    @ViewBuilder
    private var papers: some View {
        if let checklist = model.papers {
            VStack(alignment: .leading, spacing: Spacing.xs) {
                Text(strings["vehicle.documents.title"])
                    .velroFont(.heading, weight: .medium)
                    .foregroundStyle(Palette.onSurface)
                Text(strings["vehicle.documents.subtitle"])
                    .velroFont(.caption)
                    .foregroundStyle(Palette.onSurfaceVariant)
            }
            .padding(.top, Spacing.sm)
            ForEach(checklist.required, id: \.self) { type in
                let current = checklist.current(type)
                PaperRow(
                    typeCode: type,
                    status: current?.status,
                    uploadedAt: current?.uploadedAt,
                    expiresOn: current?.expiresOn,
                    rejectionReason: current?.rejectionReason,
                    uploading: model.uploadingPaper == type,
                    enabled: model.uploadingPaper == nil
                ) { file in Task { await model.uploadPaper(type, file) } }
            }
        }
    }

    private var form: some View {
        VStack(alignment: .leading, spacing: Spacing.md) {
            Text(strings["driver.vehicle.type"])
                .velroFont(.label)
                .foregroundStyle(Palette.onSurfaceVariant)
            FlowLayout(spacing: Spacing.sm) {
                ForEach(model.types) { type in
                    ChoiceChip(label: strings[type.nameKey], selected: model.typeCode == type.code) { model.typeCode = type.code }
                }
            }
            VelroField(label: strings["driver.vehicle.plate"], text: $model.plate, placeholder: strings["driver.vehicle.plate_hint"], identifier: "vehicle.plate")
            VelroField(label: strings["driver.vehicle.seats"], text: $model.seats, keyboard: .numberPad, identifier: "vehicle.seats")
            VelroField(label: strings["driver.vehicle.brand"], text: $model.brand, identifier: "vehicle.brand")
            VelroField(label: strings["driver.vehicle.model"], text: $model.model, identifier: "vehicle.model")
            VelroField(label: strings["driver.vehicle.year"], text: $model.year, keyboard: .numberPad, identifier: "vehicle.year")
            VelroField(label: strings["driver.vehicle.colour"], text: $model.colour, identifier: "vehicle.colour")
            if let error = model.error { InlineError(error: error) }
            PrimaryButton(label: strings["driver.vehicle.save"], enabled: model.canSubmit, loading: model.isSaving) {
                Task { await model.submit() }
            }
            .accessibilityIdentifier("vehicle.save")
            if model.vehicle != nil {
                SecondaryButton(label: strings["common.action.cancel"]) {
                    model.fill(from: model.vehicle)
                    model.isEditing = false
                }
            }
        }
    }

    private func statusKey(_ status: VehicleStatus) -> String {
        switch status {
        case .active: "driver.vehicle.active"
        case .pending: "driver.vehicle.awaiting"
        case .suspended: "driver.vehicle.suspended"
        case .retired: "driver.vehicle.retired"
        }
    }
}
