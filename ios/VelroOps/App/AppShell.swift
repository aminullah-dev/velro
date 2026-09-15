import SwiftUI
import VelroCore

/// The signed-in console: a sidebar on iPad and Mac, five tabs on iPhone.
///
/// Every destination sits in its own `NavigationStack`, so a feature pushes
/// its detail screens with `NavigationLink(value:)` and its own
/// `.navigationDestination(for:)`.
struct AppShell: View {
    @Environment(OpsModel.self) private var ops
    #if os(iOS)
    @Environment(\.horizontalSizeClass) private var sizeClass
    #endif

    var body: some View {
        content
            .safeAreaInset(edge: .top, spacing: 0) {
                if ops.isOffline { OfflineBanner() }
            }
            // The sidebar's badges: the dashboard's counts, once a minute.
            .poll(every: .seconds(60)) { [ops] in
                await ops.refreshAttention()
            }
    }

    @ViewBuilder private var content: some View {
        #if os(iOS)
        if sizeClass == .compact {
            PhoneShell()
        } else {
            SplitShell()
        }
        #else
        SplitShell()
        #endif
    }
}

/// iPad and Mac: the admin panel's sidebar, in its order, Settings last.
private struct SplitShell: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings

    var body: some View {
        @Bindable var navigator = ops.navigator
        NavigationSplitView {
            List(selection: $navigator.selection) {
                Section {
                    ForEach(ops.visibleRoutes.filter { $0 != .settings }) { route in
                        RouteLabel(route: route, badge: ops.badge(for: route))
                            .tag(route)
                    }
                }
                Section {
                    RouteLabel(route: .settings, badge: 0)
                        .tag(Route.settings)
                }
            }
            .navigationTitle(strings["ops.title"])
            .navigationSplitViewColumnWidth(min: 210, ideal: 250, max: 320)
        } detail: {
            let route = navigator.selection ?? Route.home(for: ops.access)
            NavigationStack {
                route.destination
            }
            // A fresh stack for each place, so the last one's pushes do not
            // leak into the next.
            .id(route)
        }
    }
}

/// iPhone: Command centre, Queues, Operations, Directory, More.
private struct PhoneShell: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings

    var body: some View {
        @Bindable var navigator = ops.navigator
        TabView(selection: $navigator.tab) {
            ForEach(OpsTab.visible(for: ops.access)) { tab in
                NavigationStack(path: $navigator[dynamicMember: OpsNavigator.pathKey(tab)]) {
                    TabRoot(tab: tab)
                        .navigationDestination(for: Route.self) { route in
                            route.destination
                        }
                }
                .tabItem { Label(strings[tab.titleKey], systemImage: tab.symbol) }
                .badge(badge(for: tab))
                .tag(tab)
            }
        }
    }

    private func badge(for tab: OpsTab) -> Int {
        tab.routes.filter { ops.can($0) }.reduce(0) { $0 + ops.badge(for: $1) }
    }
}

/// A tab's first screen: its one route itself, or a list of its routes.
private struct TabRoot: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    let tab: OpsTab

    var body: some View {
        let routes = tab.routes.filter { ops.can($0) }
        if routes.count == 1, let only = routes.first {
            only.destination
        } else {
            List(routes) { route in
                NavigationLink(value: route) {
                    RouteLabel(route: route, badge: ops.badge(for: route))
                }
            }
            .navigationTitle(strings[tab.titleKey])
        }
    }
}

/// A route's name and symbol, with what waits in it.
private struct RouteLabel: View {
    @Environment(\.strings) private var strings
    let route: Route
    let badge: Int

    var body: some View {
        Label(strings[route.titleKey], systemImage: route.symbol)
            .badge(badge > 0 ? Text(OpsFormat.count(badge, strings)) : nil)
    }
}
