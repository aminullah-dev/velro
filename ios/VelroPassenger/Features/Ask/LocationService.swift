import CoreLocation
import Observation

/// One position, when asking for a ride, and nothing else.
///
/// The server's fence is the judge of what a missing position means, not the
/// app: a refused or failed fix sends the ask without coordinates, and the
/// answer comes back in the passenger's language. What the app owns is the
/// permission -- saying why before iOS asks, and pointing at Settings once iOS
/// has stopped asking.
@MainActor
@Observable
final class LocationService: NSObject, CLLocationManagerDelegate {
    enum Access { case granted, askable, denied }

    private(set) var access: Access = .askable
    private let manager = CLLocationManager()
    private var permissionWaiter: CheckedContinuation<Void, Never>?
    private var fixWaiter: CheckedContinuation<CLLocation?, Never>?

    override init() {
        super.init()
        manager.delegate = self
        // Kilometres are plenty for a fence twenty kilometres wide, and a
        // coarse fix arrives faster under a tin roof.
        manager.desiredAccuracy = kCLLocationAccuracyKilometer
        access = Self.access(for: manager.authorizationStatus)
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
        guard access == .granted else { return nil }
        return await withCheckedContinuation { waiter in
            fixWaiter = waiter
            manager.requestLocation()
            Task { [weak self] in
                try? await Task.sleep(for: timeout)
                self?.finishFix(nil)
            }
        }
    }

    private func finishFix(_ location: CLLocation?) {
        fixWaiter?.resume(returning: location)
        fixWaiter = nil
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
            access = Self.access(for: status)
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
