import Observation
import SwiftUI
import VelroCore

/// Dashboard: the ten-second read (AdminAPI.dashboard) -- now, needs
/// attention, today, the week, drivers, money, the apps, the network.
///
/// The web panel's operations centre (admin/src/pages/Dashboard.tsx), card
/// for card and in its order: the four questions an operator asks -- what is
/// happening now, what needs me, how is today going, is the network in
/// order -- with money, drivers, the last seven days and the app versions.
/// Every number that means "act" opens the list it was counted from.
struct DashboardView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @State private var model = DashModel()

    init() {}

    var body: some View {
        Group {
            switch model.state {
            case .loading:
                LoadingView()
            case .failed(let error):
                ErrorView(error: error) { [model, ops] in await model.load(ops) }
            case .loaded(let snapshot):
                DashContent(snapshot: snapshot, refreshError: model.refreshError) { [model, ops] in
                    await model.load(ops)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Palette.background)
        .navigationTitle(strings["admin.nav.dashboard"])
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task { [model, ops] in await model.load(ops) }
                } label: {
                    if model.isRefreshing {
                        ProgressView().controlSize(.small)
                    } else {
                        Label(strings["admin.action.refresh"], systemImage: "arrow.clockwise")
                    }
                }
                .keyboardShortcut("r", modifiers: .command)
                .help(strings["admin.action.refresh"])
            }
        }
        // Left open on a screen all day: half a minute is often enough to
        // notice a departure with nobody driving it before the passenger does.
        .poll(every: .seconds(30)) { [model, ops] in
            await model.load(ops)
        }
    }
}

/// The last answer, and whether a refresh is on its way.
@MainActor
@Observable
final class DashModel {
    private(set) var state: LoadState<DashboardSnapshot> = .loading
    /// A refresh that failed while the last good figures stay on screen.
    private(set) var refreshError: APIError?
    private(set) var isRefreshing = false

    func load(_ ops: OpsModel) async {
        guard !isRefreshing else { return }
        isRefreshing = true
        defer { isRefreshing = false }
        let result = await ops.send(AdminAPI.dashboard())
        switch result {
        case .success:
            refreshError = nil
        case .failure(let error):
            if error == .cancelled { return }
            refreshError = state.value == nil ? nil : error
        }
        state = LoadState(result, keeping: state)
    }
}
