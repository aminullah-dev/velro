import Foundation
import MapKit
import Observation
import SwiftUI
import VelroCore

/// The command centre's state: the last live-map answer, what is selected,
/// the filter and search, and whether asking again is any use.
@MainActor
@Observable
final class FleetModel {
    enum Mode: String, CaseIterable, Identifiable {
        case map, list
        var id: String { rawValue }
    }

    /// An answer that asking again will not change: the role has no map
    /// (403), or the server has none to give (404). Polling stops for both.
    enum Settled: Equatable {
        case forbidden, unsupported
    }

    private(set) var state: LoadState<LiveMap> = .loading
    /// A refresh that failed while older positions stay on screen.
    private(set) var refreshError: APIError?
    private(set) var settled: Settled?
    private(set) var isRefreshing = false

    var mode: Mode = .map
    var filter: FleetFilter = .all
    var search = ""
    var selectedID: String?
    /// The camera. Set once to the region and then only by the operator (or
    /// the two framing buttons): a refresh never moves it.
    var camera: MapCameraPosition = .region(FleetRegion.region)
    /// What the camera last showed, from the map itself: after the operator
    /// pans, `camera` no longer carries a region to read.
    var visibleRegion: MKCoordinateRegion = FleetRegion.region

    var snapshot: LiveMap? { state.value }
    var drivers: [LiveDriver] { snapshot?.drivers ?? [] }

    var selected: LiveDriver? {
        guard let selectedID else { return nil }
        return drivers.first { $0.driverId == selectedID }
    }

    /// Passes the chip and the search.
    func isShown(_ driver: LiveDriver) -> Bool {
        filter.matches(driver) && FleetSearch.matches(driver, query: search)
    }

    var visible: [LiveDriver] { drivers.filter(isShown) }

    func count(_ filter: FleetFilter) -> Int {
        drivers.filter { filter.matches($0) && FleetSearch.matches($0, query: search) }.count
    }

    func load(_ ops: OpsModel) async {
        guard settled == nil, !isRefreshing else { return }
        isRefreshing = true
        defer { isRefreshing = false }
        let result = await ops.send(AdminAPI.liveMap())
        switch result {
        case .success(let map):
            refreshError = nil
            if state.value == nil {
                // The first answer replaces the spinner at once: a fade here
                // is only a slower map, and a Mac window behind another app
                // does not run it to the end.
                state = .loaded(map)
            } else {
                // The positions glide to their new places rather than jumping.
                withAnimation(.easeInOut(duration: 0.9)) {
                    state = .loaded(map)
                }
            }
            // A driver who went offline closes his panel, as the web popup does.
            if let selectedID, !map.drivers.contains(where: { $0.driverId == selectedID }) {
                self.selectedID = nil
            }
        case .failure(let error):
            if error.httpStatus == 403 {
                settled = .forbidden
            } else if error.httpStatus == 404 {
                settled = .unsupported
            } else if error == .cancelled {
                return
            }
            refreshError = state.value == nil ? nil : error
            state = LoadState(result, keeping: state)
        }
    }

    func retry(_ ops: OpsModel) async {
        settled = nil
        await load(ops)
    }

    // MARK: The camera

    func frameRegion() {
        withAnimation(.easeInOut(duration: 0.6)) { camera = .region(FleetRegion.region) }
    }

    /// Fits the cars in the service area that pass the filter; none, and the
    /// map goes back to the region.
    func fitCars() {
        let points = visible.filter(\.isInServiceArea).compactMap(\.coordinate)
        guard let region = FleetRegion.fitting(points) else { return frameRegion() }
        withAnimation(.easeInOut(duration: 0.6)) { camera = .region(region) }
    }

    /// Moves the camera to a region the map worked out itself -- the pan
    /// that brings a picked car out from under the phone's panel.
    func move(to region: MKCoordinateRegion) {
        withAnimation(.easeInOut(duration: 0.5)) { camera = .region(region) }
    }

    /// From the list: back to the map, on this car.
    func showOnMap(_ driver: LiveDriver) {
        selectedID = driver.driverId
        mode = .map
        guard let coordinate = driver.coordinate else { return }
        let current = visibleRegion.span
        let span = MKCoordinateSpan(
            latitudeDelta: min(current.latitudeDelta, 0.08),
            longitudeDelta: min(current.longitudeDelta, 0.08)
        )
        withAnimation(.easeInOut(duration: 0.6)) {
            camera = .region(MKCoordinateRegion(center: coordinate, span: span))
        }
    }
}
