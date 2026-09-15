import Observation
import SwiftUI
import VelroCore

/// Where the console is showing, on either shell.
///
/// A feature moves to another place with `navigator.open(.trips, filter:
/// "overdue")` -- the sidebar's selection changes on iPad and Mac, the tab
/// and its stack on iPhone. The filter is a hint the destination reads once
/// with `takeFilter(for:)`; the values each list understands are its own to
/// define (the dashboard's cards suggest "overdue", "active", "unassigned",
/// "departing:2", "stale_gps", "pending").
///
/// Inside a feature, push its own detail screens with `NavigationLink(value:)`
/// and `.navigationDestination(for:)`: every destination already sits in a
/// `NavigationStack`.
@MainActor
@Observable
final class OpsNavigator {
    /// The sidebar's selection (iPad, Mac).
    var selection: Route?
    /// The selected tab (iPhone).
    var tab: OpsTab = .commandCentre

    // One stack per tab, so switching tabs keeps each one where it was.
    var commandCentrePath = NavigationPath()
    var queuesPath = NavigationPath()
    var operationsPath = NavigationPath()
    var directoryPath = NavigationPath()
    var morePath = NavigationPath()

    private var filters: [Route: String] = [:]

    /// Whether this person may open a route. Set by the console from the
    /// roles, so a tab is counted the way TabRoot counts it.
    @ObservationIgnored var canOpen: @MainActor (Route) -> Bool = { _ in true }

    /// Go to a place, optionally with a filter for it to apply.
    func open(_ route: Route, filter: String? = nil) {
        if let filter { filters[route] = filter }
        selection = route
        tab = route.tab
        var path = NavigationPath()
        // A tab of several routes -- of those this person may open -- lists
        // them, and the route is pushed onto it; a tab of one is the route.
        if route.tab.routes.filter(canOpen).count > 1 { path.append(route) }
        let key = Self.pathKey(route.tab)
        if filter != nil, !path.isEmpty, self[keyPath: key] == path {
            // That screen is already showing: it keeps its state and would
            // never read the filter. Pop it now and push it again on the next
            // turn, so a new one reads it.
            self[keyPath: key] = NavigationPath()
            Task { @MainActor [weak self] in self?[keyPath: key] = path }
        } else {
            self[keyPath: key] = path
        }
    }

    /// The filter `open` left for this route, once.
    func takeFilter(for route: Route) -> String? {
        filters.removeValue(forKey: route)
    }

    /// Back to the start: after signing in, signing out, or losing a role.
    func reset(for access: StaffAccess) {
        let home = Route.home(for: access)
        selection = home
        tab = home.tab
        for tab in OpsTab.allCases { self[keyPath: Self.pathKey(tab)] = NavigationPath() }
        filters = [:]
    }

    static func pathKey(_ tab: OpsTab) -> ReferenceWritableKeyPath<OpsNavigator, NavigationPath> {
        switch tab {
        case .commandCentre: \.commandCentrePath
        case .queues: \.queuesPath
        case .operations: \.operationsPath
        case .directory: \.directoryPath
        case .more: \.morePath
        }
    }
}
