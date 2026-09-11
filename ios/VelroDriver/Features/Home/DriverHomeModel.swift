import Foundation
import Observation
import UIKit
import VelroCore

/// The driver's working screen: online or not, the trip that is his, the
/// passengers waiting, and what he has earned. Android's
/// `DriverHomeViewModel`, with its rules read from VelroCore.
@MainActor
@Observable
final class DriverHomeModel {
    private(set) var profile: DriverProfile?
    /// Signed in, but not a driver yet: everybody's first minute in this app.
    /// The apply form, not an error with a retry that retries a 403 for ever.
    private(set) var notADriver = false
    private(set) var assignment: CurrentAssignment?
    private(set) var tripMap: TripMap?
    private(set) var dispatchOffers: [DispatchOffer] = []
    /// Who is waiting, fetched whether or not he is online: it is what turns
    /// "you are offline" from a status into a reason to switch on.
    private(set) var waiting: [RideRequest] = []
    private(set) var earnings: Earnings?
    private(set) var inbox: Inbox?

    private(set) var isLoading = true
    /// The last read did not fully succeed, so what is on screen is older
    /// than it looks: the difference between "nobody is waiting" and "I could
    /// not ask".
    private(set) var isStale = false
    private(set) var isBusy = false
    private(set) var error: APIError?

    var verifyingCode = "" { didSet { if verifyingCode.count > 8 { verifyingCode = String(verifyingCode.prefix(8)) } } }
    private(set) var lastVerified: String?
    /// Bookings he has already scored, so the stars do not invite a second
    /// attempt the server would refuse. A guard against a double tap, not a
    /// record: the server keeps the one rating per booking.
    private(set) var ratedBookings: Set<String> = []
    /// A sentence to show once: a trip completed, a passenger boarded, new
    /// requests arrived.
    var notice: String?

    let app: AppModel
    /// Moves every time he flips the switch. A refresh that set off before the
    /// flip carries the old number and may not write the old availability
    /// back over his choice -- on Android exactly that race restarted the
    /// on-duty service for a driver who had just gone offline.
    private var generation = 0

    private static let profileKey = "driver-me"
    private static let earningsKey = "driver-earnings"

    init(app: AppModel) {
        self.app = app
        if let saved = app.personal.value(DriverProfile.self, key: Self.profileKey) {
            profile = saved
            isLoading = false
        }
        earnings = app.personal.value(Earnings.self, key: Self.earningsKey)
    }

    var isOnline: Bool { profile?.isOnline == true }
    var canWork: Bool { profile?.canWork == true }

    /// The road's next warning ahead of him, for the top of the ride map.
    var roadAhead: RoadAhead.Next? {
        guard let map = tripMap, let fix = app.duty.position else { return nil }
        return RoadAhead.next(
            road: map.road,
            car: (fix.coordinate.latitude, fix.coordinate.longitude),
            alerts: map.alerts ?? []
        )
    }

    // MARK: Reading

    func refresh() async {
        let started = generation
        let result = await app.client.send(API.driverProfile(), caching: Self.profileKey, in: app.personal)
        if result.error?.code == "PERMISSION_DENIED" {
            notADriver = true
            profile = nil
            isLoading = false
            error = nil
            return
        }
        notADriver = false
        if started == generation, let fresh = result.value { profile = fresh }
        isLoading = false
        if profile == nil {
            error = result.error == .cancelled ? error : result.error
            return
        }
        await loadWork()
    }

    func poll() async {
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(10))
            if Task.isCancelled { return }
            // Not while he is in the middle of something: a poll landing between
            // his tap and its answer would redraw the button he just pressed.
            if !isBusy { await refresh() }
        }
    }

    private func loadWork() async {
        var failed = false
        func record<T>(_ result: Result<T, APIError>) -> T? {
            switch result {
            case .success(let value): return value
            case .failure(let failure):
                if failure != .cancelled { failed = true }
                return nil
            }
        }

        // The inbox first: it is how he learns a price he offered was taken.
        if let fresh = record(await app.client.send(API.inbox())) { inbox = fresh }

        switch await app.client.sendNullable(API.currentTrip()) {
        case .success(let current):
            if current?.trip.id != assignment?.trip.id {
                tripMap = nil
                lastVerified = nil
            }
            assignment = current
            if let current, tripMap == nil, case .success(let drawn) = await app.client.send(API.tripMap(current.trip.id)) {
                tripMap = drawn
            }
            app.duty.follow(current, map: tripMap)
        case .failure(let failure):
            if failure != .cancelled { failed = true }
        }

        if assignment == nil && isOnline {
            if let offers = record(await app.client.send(API.dispatchOffers())) { dispatchOffers = offers }
        } else {
            dispatchOffers = []
        }

        if assignment == nil, let fetched = record(await app.client.send(API.openRideRequests())) {
            let before = Set(waiting.map(\.id))
            let arrived = fetched.filter { !before.contains($0.id) }
            let wasEmpty = waiting.isEmpty && before.isEmpty
            waiting = fetched
            // Something new, and he is in a position to take it. Nothing rings
            // on this phone otherwise: there is no push transport.
            if isOnline, !arrived.isEmpty, !wasEmpty {
                notice = app.strings["driver.requests.arrived", ["count": arrived.count]]
                UINotificationFeedbackGenerator().notificationOccurred(.success)
            }
        }

        let money = await app.client.send(API.earnings(), caching: Self.earningsKey, in: app.personal)
        if let value = money.value { earnings = value }
        if money.error != nil, money.error != .cancelled { failed = true }

        isStale = failed
    }

    // MARK: Acting

    func toggleOnline() async {
        guard let profile else { return }
        // The gate is checked here so the app can say why, rather than sending
        // a request the server will refuse.
        guard profile.canWork else {
            error = APIError(code: "DRIVER_NOT_APPROVED", httpStatus: 403, context: [:], requestId: nil)
            return
        }
        let target: DriverAvailability = profile.isOnline ? .offline : .online
        generation += 1
        isBusy = true
        error = nil
        let result = await app.client.send(API.setAvailability(target))
        isBusy = false
        switch result {
        case .success:
            if target == .online { app.duty.requestPermissionIfNeeded() }
            await refresh()
        case .failure(let failure):
            fail(failure)
        }
    }

    func acceptDispatch(_ tripId: String) async {
        guard let driverId = profile?.id else { return }
        await act { await self.app.client.send(API.acceptTrip(tripId, driverId: driverId)).map { _ in () } }
    }

    /// The one next step, which the lifecycle says the server will take.
    func advance() async {
        guard let trip = assignment?.trip, let target = trip.status.nextStep else { return }
        isBusy = true
        error = nil
        let result = await app.client.send(API.advanceTrip(trip.id, to: target))
        isBusy = false
        switch result {
        case .success(let outcome):
            if outcome.status == .completed {
                notice = outcome.driverEarning.map {
                    app.strings["driver.trip.completed", ["amount": MoneyFormatter.format($0, strings: app.strings)]]
                } ?? app.strings["driver.trip.completed_plain"]
            }
            await refresh()
        case .failure(let failure):
            fail(failure)
            // The app's view of the trip was stale: read it again rather than
            // leave a button that will keep failing.
            if failure.code == "TRIP_INVALID_TRANSITION" { await refresh() }
        }
    }

    /// Called off, with the reason the server asks for.
    func cancelTrip(reason: String) async {
        guard let trip = assignment?.trip else { return }
        await act { await self.app.client.send(API.advanceTrip(trip.id, to: .cancelled, reasonCode: reason)).map { _ in () } }
        if error == nil { lastVerified = nil }
    }

    func verify() async {
        guard let trip = assignment?.trip else { return }
        let code = verifyingCode.trimmingCharacters(in: .whitespaces)
        guard code.count >= 3 else { return }
        isBusy = true
        error = nil
        let result = await app.client.send(API.verifyPassenger(tripId: trip.id, code: code))
        isBusy = false
        switch result {
        case .success(let boarded):
            verifyingCode = ""
            lastVerified = boarded.number
            notice = boarded.passengerName.map { app.strings["driver.verify.boarded_named", ["name": $0]] }
                ?? app.strings["driver.verify.boarded"]
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            await refresh()
        case .failure(let failure):
            // Cleared on a wrong code: he retypes rather than edits on a small
            // keyboard.
            verifyingCode = ""
            fail(failure)
        }
    }

    func rate(bookingId: String, score: Int) async {
        guard let trip = assignment?.trip, !ratedBookings.contains(bookingId) else { return }
        // Marked before the call: the stars are a tap target, and a second tap
        // while the first is in flight would come back as a duplicate.
        ratedBookings.insert(bookingId)
        if case .failure(let failure) = await app.client.send(API.ratePassenger(tripId: trip.id, bookingId: bookingId, score: score)),
           failure != .offline {
            // Let him try again: a score that did not land is worse than none,
            // because he believes he gave it.
            ratedBookings.remove(bookingId)
        }
    }

    func markInboxRead() async {
        _ = await app.client.send(API.markInboxRead())
        if let fresh = try? await app.client.send(API.inbox()).get() { inbox = fresh }
    }

    func dismissError() { error = nil }

    private func act(_ call: @escaping () async -> Result<Void, APIError>) async {
        isBusy = true
        error = nil
        let result = await call()
        isBusy = false
        switch result {
        case .success: await refresh()
        case .failure(let failure):
            fail(failure)
            if failure.code == "TRIP_DRIVER_ALREADY_ASSIGNED" { await refresh() }
        }
    }

    private func fail(_ failure: APIError) {
        guard failure != .cancelled else { return }
        error = failure
    }
}
