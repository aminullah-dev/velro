import Observation

/// Where the passenger can go from home.
enum Route: Hashable {
    case ask
    case offers
    case booking(String)
    case track(String)
    case history
    case account
    case deleteAccount
    case reports
}

/// The navigation stack, held where every screen can reach it.
@MainActor
@Observable
final class Router {
    var path: [Route] = []

    func open(_ route: Route) { path.append(route) }

    /// Replace everything above home: a journey agreed from the offers screen
    /// lands on the booking, and back from there is home, not a list of prices
    /// that no longer matter.
    func replaceAll(with route: Route) { path = [route] }

    func home() { path = [] }

    func back() { if !path.isEmpty { path.removeLast() } }
}
