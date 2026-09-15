import SwiftUI
import VelroCore

/// The dashboard's sections, in the web panel's order.
///
/// Nothing is hidden at zero: the operator should see that a queue is empty,
/// not wonder whether the card failed to load. Order is urgency -- the thing
/// that strands a passenger in the next hour first, paperwork last.
struct DashContent: View {
    let snapshot: DashboardSnapshot
    let refreshError: APIError?
    let reload: @MainActor () async -> Void

    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Spacing.s2) {
                header
                now
                attention
                today
                if let history = snapshot.history, !history.days.isEmpty {
                    SectionHeader("admin.ops.week")
                    DashWeekCharts(history: history)
                }
                drivers
                money
                if let apps = snapshot.apps {
                    SectionHeader("admin.ops.app_versions")
                    DashAppVersions(apps: apps)
                }
                network
            }
            .padding(.horizontal, Spacing.s4)
            .padding(.bottom, Spacing.s8)
            .frame(maxWidth: 1480, alignment: .leading)
            .frame(maxWidth: .infinity)
        }
        .refreshable { await reload() }
    }

    // MARK: Sections

    private var header: some View {
        VStack(alignment: .leading, spacing: Spacing.s2) {
            if let generated = snapshot.generated {
                Text(strings["admin.ops.updated", ["time": OpsFormat.dateTime(generated, strings)]])
                    .opsFont(.caption)
                    .foregroundStyle(Palette.textMuted)
                    .monospacedDigit()
            }
            if let refreshError {
                Banner(strings.forErrorCode(refreshError.code, context: refreshError.context.arguments),
                       tone: .error, systemImage: "exclamationmark.triangle")
            }
        }
        .padding(.top, Spacing.s2)
    }

    private var now: some View {
        let live = snapshot.live
        return section("admin.ops.now") {
            StatCard("admin.stat.on_the_way", count: live.onTheWay, systemImage: "car", action: act(.trips, "active"))
            StatCard("admin.stat.at_the_station", count: live.atTheStation, systemImage: "building.2", action: act(.trips, "active"))
            StatCard("admin.stat.moving", count: live.moving, systemImage: "road.lanes", action: act(.trips, "active"))
            StatCard("admin.stat.departing_soon", count: live.departingSoon, systemImage: "clock", action: act(.trips, "departing:2"))
        }
    }

    private var attention: some View {
        let a = snapshot.attention
        return VStack(alignment: .leading, spacing: Spacing.s2) {
            SectionHeader("admin.ops.attention")
            if !needsAnyone {
                Banner(strings["admin.ops.all_clear"], tone: .info, systemImage: "checkmark.circle")
            }
            DashGrid {
                StatCard("admin.stat.departures_at_risk", count: a.departuresAtRisk, noteKey: "admin.stat.at_risk_hint",
                         attention: true, action: act(.dispatch, "at_risk"))
                StatCard("admin.stat.unassigned", count: a.unassignedTrips, attention: true, action: act(.dispatch, "unassigned"))
                StatCard("admin.stat.overdue", count: a.overdueTrips, noteKey: "admin.stat.overdue_hint",
                         attention: true, action: act(.trips, "overdue"))
                StatCard("admin.stat.unanswered_requests", count: a.unansweredRequests, attention: true,
                         action: act(.liveRequests, "unanswered"))
                StatCard("admin.stat.open_requests", count: a.openRequests, action: act(.liveRequests))
                StatCard("admin.stat.stale_gps", count: a.staleGpsDrivers, attention: true, action: act(.drivers, "stale_gps"))
                StatCard("admin.stat.drivers_pending", count: a.pendingDrivers, attention: true,
                         action: act(.driverApprovals, "pending"))
                StatCard("admin.vehicles.pending", count: a.pendingVehicles, attention: true,
                         action: act(.vehicleApprovals, "pending"))
                StatCard("admin.stat.pending_documents", count: a.pendingDocuments, attention: true,
                         action: act(.driverApprovals, "pending"))
                StatCard("admin.stat.open_tickets", count: a.openTickets, attention: true, action: act(.support))
                StatCard("admin.stat.settlements_open", count: snapshot.finance.settlementsOpen, attention: true,
                         action: act(.payouts))
                StatCard("admin.stat.expiring_documents", count: a.expiringDocuments, action: act(.drivers))
            }
        }
    }

    private var today: some View {
        let t = snapshot.today
        let c = snapshot.capacity
        return section("admin.ops.today") {
            StatCard("admin.stat.trips_today", count: t.trips, action: act(.trips))
            StatCard("admin.stat.bookings_today", count: t.bookings)
            StatCard("admin.stat.completed_today", count: t.completedTrips)
            StatCard("admin.stat.cancellations_today", count: t.cancellations)
            if let percent = t.utilisationPercent {
                // Digits and a slash have no direction of their own: without
                // a leading right-to-left mark the line is laid out left to
                // right and a Dari reader meets the capacity first ("12 / 1").
                // StatCard's note is a message key; an unknown key reads as
                // itself, so the already-written percentage shows as the note.
                let mark = strings.locale.isRTL ? "\u{200F}" : ""
                StatCard("admin.stat.utilisation",
                         text: mark + OpsFormat.count(t.seatsSold, strings) + " / " + OpsFormat.count(t.seatsCapacity, strings),
                         noteKey: OpsFormat.percent(percent, strings))
            } else {
                StatCard("admin.stat.utilisation", percent: nil)
            }
            StatCard("admin.stat.nearly_full", count: c.nearlyFullTrips, action: act(.trips, "departing:24"))
            StatCard("admin.stat.empty_departures", count: c.emptyDepartures, action: act(.trips, "departing:3"))
        }
    }

    private var drivers: some View {
        let d = snapshot.drivers
        return section("admin.nav.drivers") {
            StatCard("admin.stat.drivers_online", count: d.online, systemImage: "antenna.radiowaves.left.and.right",
                     action: ops.can(.commandCentre) ? act(.commandCentre) : act(.drivers))
            StatCard("admin.stat.drivers_on_trip", count: d.onTrip, systemImage: "car.fill", action: act(.trips, "active"))
            StatCard("admin.stat.drivers_offline", count: d.offline)
            StatCard("admin.stat.stale_gps", count: d.withoutFix, attention: true, action: act(.drivers, "stale_gps"))
            StatCard("admin.stat.drivers_pending", count: d.pending, attention: true, action: act(.driverApprovals, "pending"))
            StatCard("admin.stat.drivers_suspended", count: d.suspended)
            StatCard("admin.stat.passengers", count: snapshot.people.passengers, systemImage: "person.2")
        }
    }

    private var money: some View {
        let f = snapshot.finance
        return section("admin.ops.money") {
            StatCard("admin.stat.revenue_today", money: f.revenueToday)
            StatCard("admin.stat.commission_today", money: f.commissionToday)
            StatCard("admin.stat.driver_earnings_today", money: f.driverEarningsToday)
            StatCard("admin.stat.cash_owed", money: f.cashOwed)
            StatCard("admin.finance.pending_settlement", money: f.payoutsDue)
            StatCard("admin.stat.settlements_open", count: f.settlementsOpen, attention: true, action: act(.payouts))
        }
    }

    /// Routes, stations and villages have no screen in this app yet: their
    /// cards count, and the web panel is where they are edited.
    private var network: some View {
        let n = snapshot.network
        return section("admin.ops.network") {
            StatCard("admin.stat.routes_active", count: n.routesActive)
            StatCard("admin.section.stations", count: n.stations)
            StatCard("admin.section.villages", count: n.villages)
            StatCard("admin.stat.villages_without_coordinates", count: n.villagesWithoutCoordinates, attention: true)
            StatCard("admin.stat.villages_without_stations", count: n.villagesWithoutStations, attention: true)
            StatCard("admin.stat.stations_without_routes", count: n.stationsWithoutRoutes, attention: true)
            StatCard("admin.stat.routes_without_trips", count: n.routesWithoutUpcomingTrips)
        }
    }

    // MARK: Helpers

    /// The web panel's test: anything at all that asks somebody to act,
    /// papers running out and settlements included.
    private var needsAnyone: Bool {
        let a = snapshot.attention
        let sum = a.departuresAtRisk + a.unassignedTrips + a.overdueTrips + a.unansweredRequests
            + a.staleGpsDrivers + a.pendingDrivers + a.pendingVehicles + a.pendingDocuments
            + a.openTickets + a.expiringDocuments + snapshot.finance.settlementsOpen
        return sum > 0
    }

    /// Opens the list a card was counted from -- only where these roles may
    /// go; otherwise the card is a figure without a link.
    private func act(_ route: Route, _ filter: String? = nil) -> (() -> Void)? {
        guard ops.can(route) else { return nil }
        let navigator = ops.navigator
        return { navigator.open(route, filter: filter) }
    }

    private func section<Cards: View>(_ titleKey: String, @ViewBuilder cards: () -> Cards) -> some View {
        VStack(alignment: .leading, spacing: Spacing.s2) {
            SectionHeader(titleKey)
            DashGrid(content: cards)
        }
    }
}

/// Cards in columns as wide as fit: two on an iPhone, four and more on an
/// iPad or a Mac.
struct DashGrid<Content: View>: View {
    private let minimum: CGFloat
    private let content: Content

    init(minimum: CGFloat = 158, @ViewBuilder content: () -> Content) {
        self.minimum = minimum
        self.content = content()
    }

    var body: some View {
        LazyVGrid(
            columns: [GridItem(.adaptive(minimum: minimum), spacing: Spacing.s3, alignment: .top)],
            alignment: .leading,
            spacing: Spacing.s3
        ) {
            content
        }
        // One row, one height: a card with a note does not stand taller
        // than the card beside it.
        .environment(\.statCardFillsRow, true)
    }
}
