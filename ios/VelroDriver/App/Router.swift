import Observation

/// Where the driver can go from home. The same destinations as the Android
/// app's `DriverNavHost`.
enum Route: Hashable {
    case board
    case documents
    case vehicle
    case earnings
    case profile
    case deleteAccount
    case reports
}

/// The navigation stack, held where every screen can reach it.
@MainActor
@Observable
final class Router {
    var path: [Route] = []

    func open(_ route: Route) { path.append(route) }

    func home() { path = [] }

    func back() { if !path.isEmpty { path.removeLast() } }
}
