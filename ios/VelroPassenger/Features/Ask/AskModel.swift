import Foundation
import Observation
import VelroCore

/// Asking for a ride, sections 89 and 112: where from, destination, then a
/// price and a time. "Where from" opens on the passenger's own position (ADR
/// 0015) -- the nearest station, its district, and a name for the spot if she
/// gives one -- with district, village and station one tap away for the phone
/// with no fix. One model for the whole flow, because the steps share almost
/// all of their data.
///
/// There is no results step and no "search": VELRO does not price a journey,
/// so the passenger names a price and drivers answer (ADR 0004, ADR 0009).
@MainActor
@Observable
final class AskModel {
    enum Step: Int, CaseIterable {
        case origin, district, village, station, destination, ask

        var titleKey: String {
            switch self {
            case .origin: "origin.title"
            case .district: "location.label.district"
            case .village: "location.label.village"
            case .station: "location.label.station"
            case .destination: "home.question.to"
            case .ask: "ride.ask.title"
            }
        }
    }

    /// Where "current location" stands.
    enum Here { case idle, locating, found, unavailable }

    /// The place this ask comes from, when she named or chose one. `pending`
    /// is a name nobody at VELRO has read yet: the driver of this request
    /// sees it, other passengers do not.
    struct OriginPlace: Equatable {
        let id: String
        let name: String
        var pending = false
    }

    private(set) var step: Step = .origin
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

    // Where from, by position.
    private(set) var here: Here = .idle
    private(set) var fix: LocationService.Fix?
    private(set) var whereabouts: Whereabouts?
    var placeName = "" {
        didSet {
            placeRefusal = nil
            scheduleSuggestions()
        }
    }
    /// Places already named here whose name begins with what she is typing:
    /// the few letters of a known spot bring its whole name -- and the station
    /// and coordinates behind it -- back, rather than making her type it out or
    /// mint a second row for a place the valley already knows.
    private(set) var placeSuggestions: [Place] = []
    private var suggestTask: Task<Void, Never>?
    private(set) var isNamingPlace = false
    /// The server's reason for not keeping the name, or "coarse".
    private(set) var placeRefusal: String?
    private(set) var originPlace: OriginPlace?
    /// From the card or a recent, rather than browsed: decides where Back
    /// from the destination list goes.
    private(set) var originFromHere = false
    private(set) var recents: [RecentOrigin] = []

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

    /// Where the bar stands, counted along the path actually taken: from here
    /// it is three steps -- where, where to, how much -- and "step 5 of 6"
    /// after one tap would say she had skipped something.
    var progress: (current: Int, total: Int) {
        guard originFromHere || step == .origin else { return (step.rawValue, Step.allCases.count) }
        switch step {
        case .destination: return (1, 3)
        case .ask: return (2, 3)
        default: return (0, 3)
        }
    }

    /// Whether this fix may name the spot; the server refuses a vaguer one.
    var canNamePlace: Bool {
        here == .found && Naming.canName(accuracyM: fix?.accuracyM, inside: whereabouts?.inside == true)
    }

    var shownVillages: [Village] { villages.filter { $0.matches(villageFilter) } }

    /// The step has nothing to show, so a failure fills the screen instead of
    /// sitting above an empty list.
    var isEmptyForStep: Bool {
        switch step {
        case .origin: false
        case .district: districts.isEmpty
        case .village: villages.isEmpty
        case .station: stations.isEmpty
        case .destination: destinationGroups.isEmpty
        case .ask: false
        }
    }

    func start() async {
        recents = loadRecents()
        // What is saved first, so the list is there even with no signal.
        districts = app.geography.districts
        isLoading = districts.isEmpty
        let failure = await app.geography.refresh(using: app.client)
        districts = app.geography.districts
        isLoading = false
        // Only an error if there is nothing saved to show.
        error = districts.isEmpty ? failure : nil
    }

    // MARK: Where from

    /// Find where she is: one precise fix, then the server's reading of it.
    func locate(using location: LocationService) async {
        guard here != .locating else { return }
        here = .locating
        guard let found = await location.preciseFix() else {
            here = .unavailable
            return
        }
        fix = found
        switch await app.client.send(API.resolve(latitude: found.latitude, longitude: found.longitude)) {
        case .success(let reading):
            whereabouts = reading
            here = .found
        case .failure:
            // Offline or refused: the card says it could not find her, and
            // the list is right below it. No banner over a flow that works.
            here = .unavailable
        }
    }

    /// Keep the typed name. True when there is now nothing standing in the
    /// way of travelling: saved, or nothing typed to save.
    @discardableResult
    func savePlaceName() async -> Bool {
        let typed = placeName.trimmingCharacters(in: .whitespacesAndNewlines)
        if typed.isEmpty || originPlace?.name == typed { return true }
        guard !isNamingPlace, let fix else { return true }
        guard canNamePlace else {
            placeRefusal = "coarse"
            return false
        }
        isNamingPlace = true
        defer { isNamingPlace = false }
        let naming = PlaceNaming(name: typed, latitude: fix.latitude, longitude: fix.longitude, accuracyM: fix.accuracyM)
        switch await app.client.send(API.namePlace(naming)) {
        case .success(let place):
            originPlace = OriginPlace(id: place.id, name: place.name, pending: !place.isApproved)
            placeName = place.name
            return true
        case .failure(let failure):
            switch failure.code {
            case "PLACE_NAME_NOT_ALLOWED":
                if case .string(let reason) = failure.context["reason"] {
                    placeRefusal = reason
                } else {
                    placeRefusal = "personal"
                }
            case "PLACE_FIX_TOO_COARSE": placeRefusal = "coarse"
            default: error = failure
            }
            return false
        }
    }

    func clearPlace() {
        originPlace = nil
        placeName = ""
        placeSuggestions = []
    }

    /// A few letters typed: after a short pause, ask the server which known
    /// places begin with them. The pause is so a four-letter name is one
    /// request, not four, and the task is cancelled the moment she types on.
    private func scheduleSuggestions() {
        let typed = placeName.trimmingCharacters(in: .whitespacesAndNewlines)
        suggestTask?.cancel()
        guard originPlace?.name != typed, typed.count >= 2 else {
            placeSuggestions = []
            return
        }
        suggestTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(250))
            guard let self, !Task.isCancelled else { return }
            await self.loadSuggestions(for: typed)
        }
    }

    private func loadSuggestions(for typed: String) async {
        let endpoint = API.searchPlaces(typed, latitude: fix?.latitude, longitude: fix?.longitude)
        guard case .success(let places) = await app.client.send(endpoint) else { return }
        // The field may have moved on while the request was out.
        guard placeName.trimmingCharacters(in: .whitespacesAndNewlines) == typed else { return }
        placeSuggestions = places
    }

    /// A suggestion tapped: this spot is already a known place, so its name,
    /// its station and its coordinates are reused -- never typed and minted a
    /// second time.
    func choose(suggestion place: Place) async {
        suggestTask?.cancel()
        placeSuggestions = []
        originPlace = OriginPlace(id: place.id, name: place.name)
        placeName = place.name
        originFromHere = true
        let station = place.nearestStationId.flatMap { app.geography.station($0) }
            ?? (whereabouts?.stations ?? []).first { $0.id == place.nearestStationId }
            ?? (whereabouts?.stations ?? []).first
        guard let station else { return }
        await choose(station)
    }

    /// Travel from here, boarding at `station`. A name typed and not yet
    /// saved is saved first -- and a refused one stops here, beside the field.
    func travelFromHere(boardingAt station: Station) async {
        guard await savePlaceName() else { return }
        originFromHere = true
        await choose(station)
    }

    /// A named place nearby, chosen instead of typed.
    func choose(_ place: Place) async {
        let stations = whereabouts?.stations ?? []
        guard let station = stations.first(where: { $0.id == place.nearestStationId }) ?? stations.first else { return }
        originPlace = OriginPlace(id: place.id, name: place.name)
        placeName = place.name
        originFromHere = true
        await choose(station)
    }

    func choose(_ recent: RecentOrigin) async {
        // The saved station when there is one; otherwise enough of it to ask
        // with -- an id and a name are all the ask sends and shows.
        let station = app.geography.station(recent.stationId)
            ?? Station(id: recent.stationId, code: "", name: recent.stationName,
                       villageId: "", districtId: recent.districtId)
        originPlace = recent.placeId.map { OriginPlace(id: $0, name: recent.placeName ?? "") }
        originFromHere = true
        await choose(station)
    }

    /// "Choose from the list": district, village, station.
    func browse() {
        originFromHere = false
        originPlace = nil
        move(to: .district)
        if districts.isEmpty { Task { await start() } }
    }

    func choose(_ district: District) {
        self.district = district
        villages = app.geography.villages(in: district.id)
        villageFilter = ""
        move(to: .village)
    }

    func choose(_ village: Village) {
        self.village = village
        originFromHere = false
        originPlace = nil
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
        case .origin: return false
        case .district: move(to: .origin, forward: false)
        case .village: move(to: .district, forward: false)
        case .station: move(to: .village, forward: false)
        case .destination:
            if originFromHere {
                move(to: .origin, forward: false)
            } else {
                // A single-station village skipped its station step on the way in.
                move(to: stations.count == 1 ? .village : .station, forward: false)
            }
        case .ask:
            form.clearAnswers()
            move(to: .destination, forward: false)
        }
        return true
    }

    func retry() async {
        error = nil
        switch step {
        case .origin: break
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
            longitude: longitude,
            originPlaceId: originPlace?.id
        )
        let key = IdempotencyKeys.ask(
            originStationId: station.id, destinationId: destination.id,
            seats: form.passengers, attemptId: attemptId
        )
        let result = await app.client.send(API.requestRide(body, idempotencyKey: key))
        isSubmitting = false
        switch result {
        case .success:
            // Remembered once it was actually used: a list of places she
            // browsed past would be noise.
            remember(RecentOrigin(
                stationId: station.id, stationName: station.name, districtId: station.districtId,
                placeId: originPlace?.id, placeName: originPlace?.name
            ))
            return true
        case .failure(let failure):
            if failure != .cancelled { error = failure }
            return false
        }
    }

    // MARK: Recents -- on this phone, in the cache wiped at sign-out

    private static let recentsKey = "recent-origins"

    private func loadRecents() -> [RecentOrigin] {
        guard let data = app.personal.load(Self.recentsKey) else { return [] }
        return (try? JSONDecoder().decode([RecentOrigin].self, from: data)) ?? []
    }

    private func remember(_ entry: RecentOrigin) {
        recents = RecentOrigin.merged(loadRecents(), with: entry)
        if let data = try? JSONEncoder().encode(recents) {
            app.personal.store(data, key: Self.recentsKey)
        }
    }

    private func move(to next: Step, forward: Bool = true) {
        self.forward = forward
        error = nil
        step = next
    }
}
