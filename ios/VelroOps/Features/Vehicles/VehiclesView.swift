import Observation
import SwiftUI
import VelroCore

/// Every vehicle, by plate (the panel's Vehicles.tsx): what kind, how many
/// seats, whose it is and whether it may carry passengers.
///
/// Other screens open it with `navigator.open(.vehicles, filter:)`:
/// "status:<VEHICLE_STATUS>" (or the bare status), "vehicle:<id>" (selects
/// it), "search:<text>".
struct VehiclesView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @State private var model = OpVehiclesModel()
    @State private var selectedID: String?

    init() {}

    var body: some View {
        OpSplitReader { isSplit in
            if isSplit {
                OpSplitLayout(listWidth: 400) {
                    list(isSplit: true)
                } detail: {
                    if let vehicle = model.vehicle(selectedID) {
                        OpVehicleDetailView(vehicle: vehicle).id(vehicle.id)
                    } else {
                        OpNothingSelected(messageKey: "ops.vehicles.choose", systemImage: "car.side")
                    }
                }
            } else {
                list(isSplit: false)
                    .navigationDestination(for: AdminVehicle.self) { vehicle in
                        OpVehicleDetailView(vehicle: model.vehicle(vehicle.id) ?? vehicle)
                    }
            }
        }
        .background(Palette.background)
        .navigationTitle(strings["admin.nav.vehicles"])
        .searchable(text: Binding(get: { model.search }, set: { model.search = $0 }),
                    prompt: Text(strings["ops.vehicles.search"]))
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                OpRefreshButton { [model, ops] in await model.load(ops) }
            }
        }
        .task { [model, ops] in
            if let chosen = model.apply(deepLink: ops.navigator.takeFilter(for: .vehicles)) { selectedID = chosen }
            await model.load(ops)
        }
        .poll(every: .seconds(60)) { [model, ops] in
            if case .loaded = model.state { await model.load(ops) }
        }
    }

    @ViewBuilder
    private func list(isSplit: Bool) -> some View {
        VStack(spacing: 0) {
            let all = model.state.value ?? []
            OpChipBar(options: [.init(value: VehicleStatus?.none, label: strings["admin.filter.all"], count: all.count)]
                      + OpVehiclesModel.statuses.map { status in
                          .init(value: VehicleStatus?.some(status),
                                label: OpText.word(status.messageKey, raw: status.rawValue, strings),
                                count: all.filter { $0.status == status }.count)
                      },
                      selection: Binding(get: { model.status }, set: { model.status = $0 }))
            Divider()
            switch model.state {
            case .loading:
                LoadingView()
            case .failed(let error):
                ErrorView(error: error) { [model, ops] in await model.load(ops) }
            case .loaded:
                let shown = model.shown
                if shown.isEmpty {
                    EmptyStateView(messageKey: "ops.vehicles.none", systemImage: "car.side")
                } else {
                    List(selection: isSplit ? $selectedID : .constant(nil)) {
                        ForEach(shown) { vehicle in
                            if isSplit {
                                OpVehicleRowView(vehicle: vehicle).tag(vehicle.id)
                            } else {
                                NavigationLink(value: vehicle) { OpVehicleRowView(vehicle: vehicle) }
                            }
                        }
                    }
                    .listStyle(.plain)
                    // Selected beside its detail: a light ground the row's own ink reads on.
                    .tint(isSplit ? Palette.bannerInfo : Palette.accent)
                    .scrollContentBackground(.hidden)
                    .refreshable { [model, ops] in await model.load(ops) }
                }
            }
        }
    }
}

// MARK: - The model

@MainActor
@Observable
final class OpVehiclesModel {
    static let statuses: [VehicleStatus] = [.active, .pending, .suspended, .retired]

    private(set) var state: LoadState<[AdminVehicle]> = .loading
    var status: VehicleStatus?
    var search = ""

    var shown: [AdminVehicle] {
        let query = search.trimmingCharacters(in: .whitespacesAndNewlines)
        let plate = OpDriversModel.plateKey(query)
        let digits = Numerals.latin(query).filter(\.isNumber)
        return (state.value ?? []).filter { vehicle in
            if let status, vehicle.status != status { return false }
            guard !query.isEmpty else { return true }
            if !plate.isEmpty, OpDriversModel.plateKey(vehicle.plateNumber).contains(plate) { return true }
            if let name = vehicle.driverName, PlaceNames.matches(name, query) { return true }
            let make = [vehicle.brand, vehicle.model].compactMap { $0 }.joined(separator: " ")
            if !make.isEmpty, make.localizedCaseInsensitiveContains(query) { return true }
            if digits.count >= 3, let phone = vehicle.driverPhone,
               phone.filter(\.isNumber).contains(digits.drop(while: { $0 == "0" })) { return true }
            return false
        }
    }

    func vehicle(_ id: String?) -> AdminVehicle? {
        guard let id else { return nil }
        return state.value?.first { $0.id == id }
    }

    func apply(deepLink: String?) -> String? {
        guard let deepLink else { return nil }
        let parts = deepLink.split(separator: ":", maxSplits: 1).map(String.init)
        let value = parts.count > 1 ? parts[1] : parts[0]
        switch parts.first?.lowercased() {
        case "vehicle": return parts.count > 1 ? value : nil
        case "search": search = value
        default:
            if let status = VehicleStatus(rawValue: value.uppercased()) { self.status = status }
        }
        return nil
    }

    func load(_ ops: OpsModel) async {
        let result = await ops.send(AdminAPI.vehicles(limit: 200))
        if case .failure(let error) = result, error == .cancelled { return }
        state = LoadState(result, keeping: state)
    }
}

// MARK: - A row

private struct OpVehicleRowView: View {
    @Environment(\.strings) private var strings
    let vehicle: AdminVehicle

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            HStack(spacing: Spacing.s2) {
                LTRText(vehicle.plateNumber)
                    .opsFont(.heading, weight: .bold)
                    .foregroundStyle(Palette.text)
                StatusChip(OpText.vehicleType(vehicle.vehicleTypeCode, strings))
                Spacer(minLength: 0)
                StatusChip(vehicle: vehicle.status)
            }
            Text(OpVehicleText.description(vehicle, strings))
                .opsFont(.body)
                .foregroundStyle(Palette.textMuted)
                .lineLimit(1)
            HStack(spacing: Spacing.s2) {
                Image(systemName: "steeringwheel").accessibilityHidden(true)
                Text(OpText.name(vehicle.driverName, strings)).lineLimit(1)
                if let phone = vehicle.driverPhone {
                    LTRText(phone)
                }
            }
            .opsFont(.caption)
            .foregroundStyle(Palette.textMuted)
        }
        .padding(.vertical, Spacing.s1)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("vehicles.row." + vehicle.plateNumber)
    }
}

// MARK: - The detail

private struct OpVehicleDetailView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    let vehicle: AdminVehicle
    @State private var papers: LoadState<VehicleChecklist> = .loading

    var body: some View {
        Form {
            Section {
                OpDetailTitle(vehicle.plateNumber, subtitle: OpVehicleText.description(vehicle, strings), isLatin: true) {
                    StatusChip(vehicle: vehicle.status)
                    StatusChip(OpText.vehicleType(vehicle.vehicleTypeCode, strings))
                }
                .padding(.vertical, Spacing.s2)
            }
            Section {
                OpField("admin.col.type", text: OpText.vehicleType(vehicle.vehicleTypeCode, strings))
                OpField("admin.col.capacity", text: OpsFormat.count(vehicle.seatCapacity, strings))
                OpField("driver.vehicle.brand", text: vehicle.brand ?? "—")
                OpField("driver.vehicle.model", text: vehicle.model ?? "—")
                OpField("driver.vehicle.colour", text: vehicle.colour ?? "—")
            }
            Section {
                OpField("admin.col.name", text: OpText.name(vehicle.driverName, strings))
                OpField("admin.col.phone") { PhoneLink(vehicle.driverPhone) }
                Button {
                    ops.navigator.open(.drivers, filter: "driver:" + vehicle.driverId)
                } label: {
                    Label(strings["admin.nav.drivers"], systemImage: Route.drivers.symbol)
                }
            } header: {
                OpFormHeader(titleKey: "admin.col.driver")
            }
            if ops.isOperations {
                Section {
                    switch papers {
                    case .loading:
                        HStack { Spacer(); ProgressView(); Spacer() }
                    case .failed(let error):
                        Text(OpText.error(error, strings)).opsFont(.body).foregroundStyle(Palette.danger)
                    case .loaded(let checklist):
                        OpPapersSummary(missing: checklist.missing)
                        ForEach(checklist.required, id: \.self) { type in
                            let document = checklist.current(type)
                            OpPaperLine(type: type, status: document?.status, expiresOn: document?.expiresOn)
                        }
                    }
                    if vehicle.status == .pending {
                        Button {
                            ops.navigator.open(.vehicleApprovals, filter: "vehicle:" + vehicle.id)
                        } label: {
                            Label(strings["admin.nav.vehicle_approvals"], systemImage: Route.vehicleApprovals.symbol)
                        }
                    }
                } header: {
                    OpFormHeader(titleKey: "vehicle.documents.title")
                }
            }
        }
        .formStyle(.grouped)
        .scrollContentBackground(.hidden)
        .background(Palette.background)
        .opNavigationTitle(vehicle.plateNumber)
        .task(id: vehicle.id) {
            guard ops.isOperations else { return }
            let result = await ops.send(AdminAPI.vehicleDocuments(vehicleId: vehicle.id))
            if case .failure(let error) = result, error == .cancelled { return }
            papers = LoadState(result, keeping: papers)
        }
    }
}
