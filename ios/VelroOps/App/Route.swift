import VelroCore

/// Every place in the console, in the admin panel's order (admin/src/App.tsx):
/// what is happening now, then what it is made of, then the money, then the
/// settings.
///
/// A feature plugs in by replacing its placeholder view -- `DashboardView`
/// in Features/Dashboard/DashboardView.swift, and so on -- keeping the type
/// name and an `init()` with no arguments. `RouteDestination.swift` maps each
/// case to that view and is the only registration point; a feature never
/// needs to edit it, or anything else in App/.
enum Route: String, CaseIterable, Identifiable, Hashable, Sendable {
    case commandCentre
    case dashboard
    case dispatch
    case trips
    case liveRequests
    case bookings
    case passengers
    case drivers
    case driverApprovals
    case vehicles
    case vehicleApprovals
    case payouts
    case support
    case finance
    case audit
    case settings

    var id: String { rawValue }

    var titleKey: String {
        switch self {
        case .commandCentre: "ops.nav.command_centre"
        case .dashboard: "admin.nav.dashboard"
        case .dispatch: "admin.nav.operations"
        case .trips: "admin.nav.trips"
        case .liveRequests: "admin.nav.negotiations"
        case .bookings: "admin.nav.bookings"
        case .passengers: "admin.stat.passengers"
        case .drivers: "admin.nav.drivers"
        case .driverApprovals: "admin.nav.approvals"
        case .vehicles: "admin.nav.vehicles"
        case .vehicleApprovals: "admin.nav.vehicle_approvals"
        case .payouts: "admin.nav.settlements"
        case .support: "admin.nav.support"
        case .finance: "admin.nav.finance"
        case .audit: "admin.nav.audit"
        case .settings: "admin.nav.settings"
        }
    }

    /// An SF Symbol.
    var symbol: String {
        switch self {
        case .commandCentre: "map"
        case .dashboard: "square.grid.2x2"
        case .dispatch: "arrow.triangle.branch"
        case .trips: "car.2"
        case .liveRequests: "hand.raised"
        case .bookings: "person.2"
        // Not bookings' person.2: two rows of the sidebar would wear one icon.
        case .passengers: "person.3"
        case .drivers: "steeringwheel"
        case .driverApprovals: "checkmark.seal"
        case .vehicles: "car.side"
        case .vehicleApprovals: "checkmark.shield"
        case .payouts: "banknote"
        case .support: "lifepreserver"
        case .finance: "chart.bar"
        case .audit: "list.bullet.rectangle"
        case .settings: "gearshape"
        }
    }

    /// The server dependency that guards the endpoints behind this place.
    enum Access: Sendable {
        case staff, operations, finance, support, admin
    }

    var access: Access {
        switch self {
        // Passengers: the server's admin/users is require_operations.
        case .commandCentre, .dispatch, .liveRequests, .driverApprovals, .vehicleApprovals, .passengers: .operations
        case .dashboard, .trips, .bookings, .drivers, .vehicles, .settings: .staff
        case .payouts, .finance: .finance
        case .support: .support
        case .audit: .admin
        }
    }

    /// Whether these roles may open it. A place whose every request would be
    /// refused is not shown at all.
    func isAllowed(for access: StaffAccess) -> Bool {
        switch self.access {
        case .staff: access.isStaff
        case .operations: access.isOperations
        case .finance: access.isFinance
        case .support: access.isSupport
        case .admin: access.isAdmin
        }
    }

    /// Where the console opens: the live map for the people who dispatch,
    /// the dashboard for everybody else.
    static func home(for access: StaffAccess) -> Route {
        access.isOperations ? .commandCentre : .dashboard
    }

    /// Its tab on an iPhone.
    var tab: OpsTab {
        switch self {
        case .commandCentre: .commandCentre
        case .dispatch, .liveRequests, .driverApprovals, .vehicleApprovals, .payouts, .support: .queues
        case .dashboard, .trips, .bookings: .operations
        case .passengers, .drivers, .vehicles: .directory
        case .finance, .audit, .settings: .more
        }
    }
}

/// The iPhone's five tabs. A tab holding one route shows it directly; one
/// holding several lists them.
enum OpsTab: String, CaseIterable, Identifiable, Hashable, Sendable {
    case commandCentre, queues, operations, directory, more

    var id: String { rawValue }

    var titleKey: String {
        switch self {
        case .commandCentre: "ops.nav.command_centre"
        case .queues: "ops.tab.queues"
        case .operations: "ops.tab.operations"
        case .directory: "ops.tab.directory"
        case .more: "ops.tab.more"
        }
    }

    var symbol: String {
        switch self {
        case .commandCentre: "map"
        case .queues: "tray.full"
        case .operations: "square.grid.2x2"
        case .directory: "person.2"
        case .more: "ellipsis.circle"
        }
    }

    var routes: [Route] { Route.allCases.filter { $0.tab == self } }

    /// The tabs with at least one route these roles may open.
    static func visible(for access: StaffAccess) -> [OpsTab] {
        allCases.filter { tab in tab.routes.contains { $0.isAllowed(for: access) } }
    }
}
