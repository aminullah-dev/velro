import AudioToolbox
import CoreLocation
import Observation
import OSLog
import UIKit
import UserNotifications
import VelroCore

/// The driver's position while he carries a trip, and the road's warnings.
///
/// The iOS half of Android's `DriverDutyService`, cut to what iOS allows and
/// a driver needs: it runs exactly while a trip is his -- never merely because
/// he is online -- with When-In-Use permission and the blue location pill
/// showing, so the passengers he is driving see the car and he is warned
/// before the switchbacks even with the phone in his pocket. Every thirty
/// seconds it sends where the car is and asks the server whether the trip is
/// still his; the moment it is not, it stops itself.
///
/// Waiting for passengers is the home screen's business, in the foreground:
/// there is no push transport, and a location feed kept alive only to poll
/// would be exactly what App Review is right to refuse.
@MainActor
@Observable
final class TripDuty: NSObject, CLLocationManagerDelegate {
    enum Access { case granted, askable, denied }

    /// The trip being carried, or nil when off duty.
    private(set) var tripId: String?
    /// The latest fix, for the ride map's "how far is the next warning".
    private(set) var position: CLLocation?
    /// The advisory zone he is inside right now, as a message key.
    private(set) var roadAlertKey: String?
    private(set) var access: Access = .askable
    /// Set by the app whenever the language changes; the warnings he hears in
    /// his pocket are in the language he chose.
    var strings = Strings(locale: .dari, translations: [:], fallback: [:])

    private let client: APIClient
    private let manager = CLLocationManager()
    private var alerts: [RoadAlert] = []
    private var announced: [String: Date] = [:]
    private var lastPing: Date?
    private var loop: Task<Void, Never>?

    static let tick: Duration = .seconds(30)
    private let log = Logger(subsystem: "af.velro.driver", category: "duty")
    static let cooldown: TimeInterval = 10 * 60

    init(client: APIClient) {
        self.client = client
        super.init()
        manager.delegate = self
        manager.activityType = .automotiveNavigation
        // Ten metres is what a passenger watching a car come round a bend can
        // see; a tighter fix costs battery he pays for.
        manager.desiredAccuracy = kCLLocationAccuracyNearestTenMeters
        manager.distanceFilter = 20
        manager.pausesLocationUpdatesAutomatically = false
        access = Self.access(for: manager.authorizationStatus)
    }

    /// Follow what the server says is his: a trip starts the feed, no trip
    /// stops it. Called on every read of the current trip, so it is
    /// idempotent -- the same trip again changes nothing.
    func follow(_ assignment: CurrentAssignment?, map: TripMap?) {
        if let map { alerts = map.alerts ?? [] }
        guard let assignment, !Self.finished(assignment.trip.status) else {
            stop()
            return
        }
        guard tripId != assignment.trip.id else { return }
        start(tripId: assignment.trip.id)
    }

    /// Ask for location, once, when he first takes work: the prompt comes with
    /// a reason he can see, not at launch.
    func requestPermissionIfNeeded() {
        if manager.authorizationStatus == .notDetermined { manager.requestWhenInUseAuthorization() }
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    func stop() {
        loop?.cancel()
        loop = nil
        guard tripId != nil else { return }
        tripId = nil
        manager.stopUpdatingLocation()
        manager.allowsBackgroundLocationUpdates = false
        roadAlertKey = nil
        position = nil
        lastPing = nil
    }

    private func start(tripId: String) {
        log.info("on duty for trip \(tripId, privacy: .public), access \(String(describing: self.access), privacy: .public)")
        self.tripId = tripId
        announced = [:]
        requestPermissionIfNeeded()
        beginUpdates()
        loop?.cancel()
        loop = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: Self.tick)
                guard let self, !Task.isCancelled else { return }
                await self.tickOnce()
            }
        }
    }

    private func beginUpdates() {
        guard access == .granted, tripId != nil else { return }
        log.info("location updates start")
        // Only while a trip is his, and only with the pill showing: he can see
        // the app is following him, and why.
        manager.allowsBackgroundLocationUpdates = true
        manager.showsBackgroundLocationIndicator = true
        manager.startUpdatingLocation()
    }

    /// The thirty-second beat: is the trip still his, and where is the car.
    private func tickOnce() async {
        guard let current = tripId else { return }
        switch await client.sendNullable(API.currentTrip()) {
        case .success(let assignment):
            // Finished, cancelled, or handed to someone else: off duty.
            if assignment?.trip.id != current || assignment.map({ Self.finished($0.trip.status) }) == true {
                stop()
                return
            }
        case .failure:
            // No signal is not the end of the trip.
            break
        }
        if let position { await ping(position) }
    }

    private func ping(_ fix: CLLocation) async {
        lastPing = .now
        _ = await client.send(API.pingLocation(
            latitude: fix.coordinate.latitude,
            longitude: fix.coordinate.longitude,
            heading: fix.course >= 0 ? fix.course : nil,
            accuracy: fix.horizontalAccuracy >= 0 ? fix.horizontalAccuracy : nil,
            at: fix.timestamp
        ))
    }

    private func received(_ fix: CLLocation) {
        guard tripId != nil else { return }
        log.debug("fix \(fix.coordinate.latitude, privacy: .public),\(fix.coordinate.longitude, privacy: .public)")
        position = fix
        watchRoad(fix)
        // The first fix of a trip goes straight away: the passenger's map
        // should not sit empty for half a minute after he sets off.
        if lastPing == nil || Date.now.timeIntervalSince(lastPing!) >= 30 {
            Task { await ping(fix) }
        }
    }

    // MARK: The road

    private func watchRoad(_ fix: CLLocation) {
        let car = (fix.coordinate.latitude, fix.coordinate.longitude)
        let now = Date.now
        let inside = alerts.filter { Eta.distance(car, ($0.latitude, $0.longitude)) <= Double($0.radiusM) }
        guard !inside.isEmpty else {
            // Written only when it changes: an @Observable property redraws
            // its readers on every write, and a fix a second rewriting nil
            // redrew the trip card under his thumb -- the code field he was
            // typing into lost its keyboard.
            if roadAlertKey != nil { roadAlertKey = nil }
            return
        }
        guard let hit = inside.first(where: { now.timeIntervalSince(announced[key($0)] ?? .distantPast) > Self.cooldown }) else {
            return
        }
        announced[key(hit)] = now
        if roadAlertKey != hit.messageKey { roadAlertKey = hit.messageKey }
        // Felt as well as heard: a ringer set to vibrate must not make the
        // warning silent.
        AudioServicesPlaySystemSound(kSystemSoundID_Vibrate)
        if UIApplication.shared.applicationState != .active {
            let content = UNMutableNotificationContent()
            content.title = strings["notif.road.title"]
            content.body = strings[hit.messageKey]
            content.sound = .default
            UNUserNotificationCenter.current().add(
                UNNotificationRequest(identifier: "velro.road", content: content, trigger: nil)
            )
        }
    }

    private func key(_ alert: RoadAlert) -> String { "\(alert.latitude):\(alert.longitude)" }

    private static func finished(_ status: TripStatus) -> Bool {
        [.completed, .cancelled, .expired, .noDriverAvailable].contains(status)
    }

    private static func access(for status: CLAuthorizationStatus) -> Access {
        switch status {
        case .authorizedWhenInUse, .authorizedAlways: .granted
        case .notDetermined: .askable
        default: .denied
        }
    }

    // CLLocationManager calls back on the thread that made it -- this one.

    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        let status = manager.authorizationStatus
        MainActor.assumeIsolated {
            let now = Self.access(for: status)
            if access != now { access = now }
            log.info("authorization \(status.rawValue, privacy: .public)")
            beginUpdates()
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let last = locations.last else { return }
        MainActor.assumeIsolated { received(last) }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: any Error) {
        let text = String(describing: error)
        MainActor.assumeIsolated { log.error("location failed: \(text, privacy: .public)") }
    }
}
