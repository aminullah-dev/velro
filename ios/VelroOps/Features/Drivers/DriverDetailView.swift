import SwiftUI
import VelroCore

/// One driver: who he is, how he drives, the car he drives it in, where his
/// papers stand -- and suspending him, or putting a suspended driver back to
/// work.
struct OpDriverDetailView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    let driver: AdminDriver
    /// The directory again, after a decision changed him.
    let onChanged: @MainActor @Sendable () async -> Void

    @State private var vehicles: LoadState<[AdminVehicle]> = .loading
    @State private var papers: LoadState<DocumentChecklist> = .loading
    @State private var confirm: ConfirmRequest?

    var body: some View {
        Form {
            Section {
                OpDetailTitle(OpText.name(driver.fullName, strings)) {
                    StatusChip(driver: driver.approvalStatus)
                    StatusChip(availability: driver.availability)
                }
                .padding(.vertical, Spacing.s2)
            }
            Section {
                OpField("admin.col.phone") { PhoneLink(driver.phone) }
                OpField("admin.col.rating", text: OpText.rating(driver.ratingAverage, count: driver.ratingCount, strings))
                OpField("driver.profile.trips", text: OpsFormat.count(driver.completedTrips, strings))
                OpField("admin.col.last_seen", text: OpsFormat.age(seconds: driver.locationAgeSeconds, strings))
            }
            vehiclesSection
            if ops.isOperations {
                papersSection
                actionsSection
            }
        }
        .formStyle(.grouped)
        .scrollContentBackground(.hidden)
        .background(Palette.background)
        .opNavigationTitle(OpText.name(driver.fullName, strings))
        .task(id: driver.id) { await load() }
        .confirmAction($confirm)
    }

    // MARK: The car

    private var vehiclesSection: some View {
        Section {
            switch vehicles {
            case .loading:
                HStack { Spacer(); ProgressView(); Spacer() }
            case .failed(let error):
                Text(OpText.error(error, strings)).opsFont(.body).foregroundStyle(Palette.danger)
            case .loaded(let cars):
                if cars.isEmpty {
                    OpField("admin.col.plate", text: "—")
                } else {
                    ForEach(cars) { car in
                        OpVehicleLine(vehicle: car)
                    }
                }
            }
        } header: {
            OpFormHeader(titleKey: "trip.label.vehicle")
        }
    }

    // MARK: Papers

    private var papersSection: some View {
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
            // The approvals queue lists only drivers still waiting: for anyone
            // else it would open the next applicant in his place.
            if driver.approvalStatus == .pending {
                Button {
                    ops.navigator.open(.driverApprovals, filter: "driver:" + driver.id)
                } label: {
                    Label(strings["admin.nav.approvals"], systemImage: Route.driverApprovals.symbol)
                }
            }
        } header: {
            OpFormHeader(titleKey: "admin.approvals.documents")
        }
    }

    // MARK: Decisions

    @ViewBuilder
    private var actionsSection: some View {
        switch driver.approvalStatus {
        case .approved:
            Section {
                Button(role: .destructive) { askSuspend() } label: {
                    Label(strings["admin.action.suspend"], systemImage: "hand.raised.slash")
                }
                .accessibilityIdentifier("driver.suspend")
            } footer: {
                Text(strings["ops.drivers.suspend_hint"])
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
            }
        case .suspended:
            Section {
                Button { askReinstate() } label: {
                    Label(strings["admin.approvals.approve_driver"], systemImage: "checkmark.seal")
                }
                .accessibilityIdentifier("driver.reinstate")
            } footer: {
                Text(strings["ops.drivers.reinstate_hint"])
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
            }
        case .pending, .rejected:
            EmptyView()
        }
    }

    private func askSuspend() {
        let id = driver.id
        confirm = ConfirmRequest(
            title: strings["admin.confirm.suspend"],
            message: OpText.name(driver.fullName, strings) + " — " + strings["ops.drivers.suspend_hint"],
            confirmTitle: strings["admin.action.suspend"],
            isDestructive: true,
            reason: .required,
            reasonPrompt: strings["ops.drivers.suspend_reason"]
        ) { [ops, onChanged] reason in
            switch await ops.send(AdminAPI.suspendDriver(id, reason: reason)) {
            case .success:
                await onChanged()
                await ops.refreshAttention()
                return nil
            case .failure(let error):
                return error
            }
        }
    }

    private func askReinstate() {
        let id = driver.id
        confirm = ConfirmRequest(
            title: strings["admin.approvals.approve_driver"],
            message: OpText.name(driver.fullName, strings) + " — " + strings["ops.drivers.reinstate_hint"],
            confirmTitle: strings["admin.action.approve"]
        ) { [ops, onChanged] _ in
            switch await ops.send(AdminAPI.approveDriver(id)) {
            case .success:
                await onChanged()
                await ops.refreshAttention()
                return nil
            case .failure(let error):
                return error
            }
        }
    }

    private func load() async {
        async let cars = ops.send(AdminAPI.vehicles(limit: 200))
        if ops.isOperations {
            let checklist = await ops.send(AdminAPI.driverDocuments(driverId: driver.id))
            if case .failure(let error) = checklist, error == .cancelled { return }
            papers = LoadState(checklist, keeping: papers)
        }
        let result = await cars
        if case .failure(let error) = result, error == .cancelled { return }
        let mine = driver.id
        vehicles = LoadState(result.map { $0.filter { $0.driverId == mine } }, keeping: vehicles)
    }
}

// MARK: - Shared with the vehicle directory

/// A car in a few lines: plate, kind, seats, make, colour, status.
struct OpVehicleLine: View {
    @Environment(\.strings) private var strings
    let vehicle: AdminVehicle

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            HStack(spacing: Spacing.s2) {
                LTRText(vehicle.plateNumber)
                    .opsFont(.body, weight: .medium)
                StatusChip(vehicle: vehicle.status)
                Spacer(minLength: 0)
                Text(OpText.vehicleType(vehicle.vehicleTypeCode, strings))
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
            }
            Text(OpVehicleText.description(vehicle, strings))
                .opsFont(.caption)
                .foregroundStyle(Palette.textMuted)
        }
        .accessibilityElement(children: .combine)
    }
}

enum OpVehicleText {
    /// "Toyota Corolla · white · 4 seats".
    static func description(_ vehicle: AdminVehicle, _ strings: Strings) -> String {
        let make = [vehicle.brand, vehicle.model].compactMap { $0?.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }.joined(separator: " ")
        var parts: [String] = []
        if !make.isEmpty { parts.append(make) }
        if let colour = vehicle.colour, !colour.isEmpty { parts.append(colour) }
        parts.append(strings["driver.vehicle.seats_count", ["count": vehicle.seatCapacity]])
        return parts.joined(separator: OpsJoin.separator(strings))
    }
}

/// "All documents verified", or what is still missing.
struct OpPapersSummary: View {
    @Environment(\.strings) private var strings
    let missing: [String]

    var body: some View {
        if missing.isEmpty {
            Label(strings["admin.approvals.complete"], systemImage: "checkmark.seal.fill")
                .opsFont(.body, weight: .medium)
                .foregroundStyle(Palette.accent)
        } else {
            VStack(alignment: .leading, spacing: 2) {
                Label(strings["admin.approvals.missing"], systemImage: "exclamationmark.triangle.fill")
                    .opsFont(.body, weight: .medium)
                    .foregroundStyle(Palette.attention)
                Text(missing.map { OpText.word("document.type." + $0.lowercased(), raw: $0, strings) }
                    .joined(separator: strings.locale.isRTL ? "، " : ", "))
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
            }
            .accessibilityElement(children: .combine)
        }
    }
}

/// One required paper and where it stands.
struct OpPaperLine: View {
    @Environment(\.strings) private var strings
    let type: String
    let status: DocumentStatus?
    let expiresOn: String?

    var body: some View {
        LabeledContent {
            HStack(spacing: Spacing.s2) {
                if let expiresOn, status == .verified {
                    DateText(expiresOn)
                        .opsFont(.caption)
                        .foregroundStyle(Palette.textMuted)
                }
                if let status {
                    StatusChip(document: status)
                } else {
                    StatusChip(strings["admin.approvals.not_uploaded"], tone: .failed)
                }
            }
        } label: {
            Text(OpText.word("document.type." + type.lowercased(), raw: type, strings))
                .opsFont(.body)
        }
        .accessibilityElement(children: .combine)
    }
}
