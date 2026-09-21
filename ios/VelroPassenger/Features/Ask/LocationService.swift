import CoreLocation
import Observation

/// One position when it is asked for, and nothing else: no updates left
/// running, nothing stored.
///
/// Two questions, two grades. The ask's fence needs only "somewhere in
/// Ghorband", and a coarse fix arrives faster under a tin roof. "Current
/// location" needs the station she can walk to and, if she names the spot, a
/// point good to a few dozen metres (ADR 0015) -- so it asks for the best the
/// phone can do, and waits longer for it.
///
/// The server's fence is the judge of what a missing position means, not the
/// app. What the app owns is the permission: saying why before iOS asks, and
/// pointing at Settings once iOS has stopped asking.
@MainActor
@Observable
final class LocationService: NSObject, CLLocationManagerDelegate {
    enum Access { case granted, askable, denied }

    struct Fix {
        let latitude: Double
        let longitude: Double
        /// The radius iOS says the fix is good to; nil when it would not say.
        let accuracyM: Double?
    }

    private(set) var access: Access = .askable
    /// False when the person switched "Precise Location" off for VELRO: iOS
    /// then answers to within a few kilometres, which finds a station but
    /// cannot name a spot.
    private(set) var isPrecise = true
    private let manager = CLLocationManager()
    private var permissionWaiter: CheckedContinuation<Void, Never>?
    /// Everyone waiting for the one fix in flight. A second caller joins the
    /// first rather than replacing it -- replacing it left the first waiting
    /// for ever, and an earlier timeout could then answer the second with nil.
    private var fixWaiters: [CheckedContinuation<CLLocation?, Never>] = []
    private var timeout: Task<Void, Never>?

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyKilometer
        access = Self.access(for: manager.authorizationStatus)
        isPrecise = manager.accuracyAuthorization == .fullAccuracy
    }

    /// Asks iOS once, if it has never been asked, and waits for the answer.
    func requestIfNeeded() async {
        guard manager.authorizationStatus == .notDetermined else { return }
        await withCheckedContinuation { waiter in
            permissionWaiter = waiter
            manager.requestWhenInUseAuthorization()
        }
    }

    /// A fix within a few seconds, or nil. Never longer: the ask must not hang
    /// on a sky the phone cannot see.
    func currentFix(timeout: Duration = .seconds(8)) async -> CLLocation? {
        await fix(accuracy: kCLLocationAccuracyKilometer, timeout: timeout)
    }

    /// The best fix the phone will give, for "current location". Longer to
    /// wait for: she is standing still, looking at a card that says it is
    /// finding her.
    func preciseFix(timeout: Duration = .seconds(15)) async -> Fix? {
        guard let location = await fix(accuracy: kCLLocationAccuracyNearestTenMeters, timeout: timeout) else {
            return nil
        }
        return Fix(
            latitude: location.coordinate.latitude,
            longitude: location.coordinate.longitude,
            accuracyM: location.horizontalAccuracy >= 0 ? location.horizontalAccuracy : nil
        )
    }

    private func fix(accuracy: CLLocationAccuracy, timeout: Duration) async -> CLLocation? {
        guard access == .granted else { return nil }
        return await withCheckedContinuation { waiter in
            fixWaiters.append(waiter)
            // Already asking: this caller waits for the same answer.
            guard fixWaiters.count == 1 else { return }
            manager.desiredAccuracy = accuracy
            manager.requestLocation()
            self.timeout = Task { [weak self] in
                try? await Task.sleep(for: timeout)
                guard !Task.isCancelled else { return }
                self?.finishFix(nil)
            }
        }
    }

    private func finishFix(_ location: CLLocation?) {
        timeout?.cancel()
        timeout = nil
        let waiting = fixWaiters
        fixWaiters = []
        for waiter in waiting { waiter.resume(returning: location) }
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
        let precise = manager.accuracyAuthorization == .fullAccuracy
        MainActor.assumeIsolated {
            access = Self.access(for: status)
            isPrecise = precise
            if status != .notDetermined {
                permissionWaiter?.resume()
                permissionWaiter = nil
            }
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        let last = locations.last
        MainActor.assumeIsolated { finishFix(last) }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: any Error) {
        MainActor.assumeIsolated { finishFix(nil) }
    }
}
