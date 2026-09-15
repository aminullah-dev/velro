import SwiftUI
import VelroCore

/// Command centre: every working driver on one map (AdminAPI.liveMap) --
/// where the cars are, what each is doing, and how old each position is.
///
/// The web panel's live map (admin/src/components/LiveMap.tsx), made the
/// whole screen: the same states, the same legend and region, the same lists
/// of drivers the map cannot show. It refreshes every 15 seconds and never
/// moves the camera on a refresh; a selected car opens its panel -- a sheet
/// on iPhone, the inspector on iPad and Mac.
struct CommandCentreView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @Environment(\.layoutDirection) private var direction
    @Environment(\.locale) private var locale
    #if os(iOS)
    @Environment(\.horizontalSizeClass) private var sizeClass
    #endif
    @State private var model = FleetModel()

    init() {}

    var body: some View {
        content
            .background(Palette.background)
            .navigationTitle(strings["ops.nav.command_centre"])
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            .toolbarBackground(.visible, for: .navigationBar)
            #endif
            .toolbar { toolbar }
            .searchable(text: $model.search, prompt: Text(strings["ops.map.search_prompt"]))
            // iPad and Mac: a column beside the map. iPhone: a sheet that
            // leaves the upper map in view and usable, as a ride app's does
            // (the inspector alone would open full height there).
            .inspector(isPresented: panelShown(asSheet: false)) {
                panel
                    .inspectorColumnWidth(min: 300, ideal: 360, max: 440)
            }
            .sheet(isPresented: panelShown(asSheet: true)) {
                panel
                    .presentationDetents([Self.sheetDetent, .large])
                    .presentationBackgroundInteraction(.enabled(upThrough: Self.sheetDetent))
                    .presentationDragIndicator(.visible)
            }
            .poll(every: .seconds(15)) { [model, ops] in
                await model.load(ops)
            }
    }

    // MARK: The screen

    @ViewBuilder private var content: some View {
        if let settled = model.settled {
            // An answer, not a fault: asking again every 15 s changes nothing.
            FleetNoticeCard(
                systemImage: settled == .forbidden ? "lock" : "map",
                text: settled == .forbidden ? strings.forErrorCode("PERMISSION_DENIED") : strings["admin.map.not_supported"]
            )
            .padding(Spacing.s6)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            switch model.state {
            case .loading:
                LoadingView()
            case .failed(let error):
                ErrorView(error: error) { [model, ops] in await model.retry(ops) }
            case .loaded(let snapshot):
                loaded(snapshot)
            }
        }
    }

    private func loaded(_ snapshot: LiveMap) -> some View {
        Group {
            switch model.mode {
            case .map: FleetMapView(model: model, snapshot: snapshot, revealsSelection: usesSheet)
            case .list: FleetListView(model: model, snapshot: snapshot)
            }
        }
        .safeAreaInset(edge: .top, spacing: 0) {
            FleetFilterBar(model: model)
                .background {
                    if model.mode == .list { Palette.background }
                }
        }
    }

    @ToolbarContentBuilder private var toolbar: some ToolbarContent {
        ToolbarItem(placement: .principal) {
            Picker(strings["ops.nav.command_centre"], selection: $model.mode.animation(.snappy)) {
                Text(strings["ops.map.view_map"]).tag(FleetModel.Mode.map)
                Text(strings["ops.map.view_list"]).tag(FleetModel.Mode.list)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .fixedSize()
        }
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
            .disabled(model.settled != nil)
        }
    }

    // MARK: The panel

    private static let sheetDetent = PresentationDetent.fraction(0.56)

    /// A phone's width: the panel is a sheet, not a column.
    private var usesSheet: Bool {
        #if os(iOS)
        sizeClass == .compact
        #else
        false
        #endif
    }

    private func panelShown(asSheet: Bool) -> Binding<Bool> {
        Binding(
            get: { model.selected != nil && usesSheet == asSheet },
            set: { shown in if !shown { model.selectedID = nil } }
        )
    }

    @ViewBuilder private var panel: some View {
        if let driver = model.selected {
            FleetDriverPanel(
                driver: driver,
                showMapAction: model.mode == .list ? { [model] in model.showOnMap(driver) } : nil,
                close: { [model] in model.selectedID = nil }
            )
            // On iPhone the inspector is a sheet, a new presentation: carry
            // the language, its direction and the console across.
            .environment(\.strings, strings)
            .environment(\.layoutDirection, direction)
            .environment(\.locale, locale)
            .environment(ops)
        }
    }
}
