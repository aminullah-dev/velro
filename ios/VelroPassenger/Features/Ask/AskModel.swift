import Foundation
import Observation
import VelroCore

/// Asking for a ride, sections 89 and 112: district, village, station,
/// destination, then a price and a time. One model for the whole flow,
/// because the steps share almost all of their data.
///
/// There is no results step and no "search": VELRO does not price a journey,
/// so the passenger names a price and drivers answer (ADR 0004, ADR 0009).
@MainActor
@Observable
final class AskModel {
    enum Step: Int, CaseIterable {
        case district, village, station, destination, ask

        var titleKey: String {
            switch self {
            case .district: "location.label.district"
            case .village: "location.label.village"
            case .station: "location.label.station"
            case .destination: "home.question.to"
            case .ask: "ride.ask.title"
            }
        }
    }

    private(set) var step: Step = .district
    /// Which way the last move went, so the panel slides the right way.
    private(set) var forward = true

    private(set) var districts: [District] = []
    private(set) var villages: [Village] = []
    private(set) var stations: [Station] = []
    private(set) var destinationGroups: [DestinationGroup] = []

    private(set) var district: District?
    private(set) var village: Village?
    private(set) var station: Station?
    private(set) var destination: Destination?
    var expandedGroupId: String?
    /// Siahgird alone has 189 villages: scrolling to find yours is no way to
    /// start a journey.
    var villageFilter = ""
    var form = AskForm(nowHour: Calendars.kabulHour())

    private(set) var isLoading = false
    private(set) var isSubmitting = false
    private(set) var error: APIError?

    /// Held for the whole visit, so a retry after a dropped connection is this
    /// same ask and does not ring every driver a second time.
    private let attemptId = IdempotencyKeys.newAttemptId()
    private let app: AppModel

    init(app: AppModel) { self.app = app }

    /// Refused for a missing position, not for being outside the area. Only
    /// this refusal gets a remedy beside it: "outside the service area" is
    /// deliberately vague, and a button under it would read as a hint.
    var needsLocationAccess: Bool { error?.code == "GEOFENCE_LOCATION_REQUIRED" }

    var canAsk: Bool { station != nil && destination != nil && form.isComplete && !isSubmitting }

    var shownVillages: [Village] { villages.filter { $0.matches(villageFilter) } }

    /// The step has nothing to show, so a failure fills the screen instead of
    /// sitting above an empty list.
    var isEmptyForStep: Bool {
        switch step {
        case .district: districts.isEmpty
        case .village: villages.isEmpty
        case .station: stations.isEmpty
        case .destination: destinationGroups.isEmpty
        case .ask: false
        }
    }

    func start() async {
        // What is saved first, so the list is there even with no signal.
        districts = app.geography.districts
        isLoading = districts.isEmpty
        let failure = await app.geography.refresh(using: app.client)
        districts = app.geography.districts
        isLoading = false
        // Only an error if there is nothing saved to show.
        error = districts.isEmpty ? failure : nil
    }

    func choose(_ district: District) {
        self.district = district
        villages = app.geography.villages(in: district.id)
        villageFilter = ""
        move(to: .village)
    }

    func choose(_ village: Village) {
        self.village = village
        stations = app.geography.stations(in: village.id)
        // A village with exactly one station does not ask.
        if stations.count == 1 {
            Task { await choose(stations[0]) }
        } else {
            move(to: .station)
        }
    }

    func choose(_ station: Station) async {
        self.station = station
        destinationGroups = []
        move(to: .destination)
        isLoading = true
        switch await app.geography.destinations(from: station.id, using: app.client) {
        case .success(let groups): destinationGroups = groups
        case .failure(let failure): error = failure
        }
        isLoading = false
    }

    func toggle(_ group: DestinationGroup) {
        if group.isChoosableItself {
            choose(group.asDestination)
        } else {
            expandedGroupId = expandedGroupId == group.id ? nil : group.id
        }
    }

    func choose(_ destination: Destination) {
        self.destination = destination
        // Re-read the hour: the flow can sit on this list while the evening
        // turns over, and the hours offered next are counted from it.
        form.nowHour = Calendars.kabulHour()
        form.clampHours()
        move(to: .ask)
    }

    /// One step back. False on the first step, where back leaves the flow.
    func back() -> Bool {
        error = nil
        switch step {
        case .district: return false
        case .village: move(to: .district, forward: false)
        case .station: move(to: .village, forward: false)
        case .destination:
            // A single-station village skipped its station step on the way in.
            move(to: stations.count == 1 ? .village : .station, forward: false)
        case .ask:
            form.clearAnswers()
            move(to: .destination, forward: false)
        }
        return true
    }

    func retry() async {
        error = nil
        switch step {
        case .district: await start()
        case .village: if let district { choose(district) }
        case .station: if let village { choose(village) }
        case .destination: if let station { await choose(station) }
        case .ask: break
        }
    }

    /// Send the ask, with the position if there is one. True when drivers
    /// are now being shown it.
    func ask(latitude: Double?, longitude: Double?) async -> Bool {
        guard canAsk, let station, let destination, let fare = form.fareMinor else { return false }
        isSubmitting = true
        error = nil
        let body = RideAsk(
            originStationId: station.id,
            destinationId: destination.id,
            passengerCount: form.passengers,
            offeredFareMinor: fare,
            returnFareMinor: form.returnFareMinor,
            note: form.note,
            requestedFor: form.requestedFor(),
            returnFor: form.returnFor(),
            latitude: latitude,
            longitude: longitude
        )
        let key = IdempotencyKeys.ask(
            originStationId: station.id, destinationId: destination.id,
            seats: form.passengers, attemptId: attemptId
        )
        let result = await app.client.send(API.requestRide(body, idempotencyKey: key))
        isSubmitting = false
        switch result {
        case .success: return true
        case .failure(let failure):
            if failure != .cancelled { error = failure }
            return false
        }
    }

    private func move(to next: Step, forward: Bool = true) {
        self.forward = forward
        error = nil
        step = next
    }
}
