import Foundation
import Observation
import VelroCore

/// Home: the ask she has open, if any, and her recent journeys.
@MainActor
@Observable
final class HomeModel {
    private(set) var bookings: [Booking] = []
    /// The ask she has open right now. Without it on home, a passenger who
    /// closed the app while drivers were bidding had no way back to her own
    /// request -- and the server refuses a second while the first is alive.
    private(set) var openRequest: RideRequest?
    private(set) var isLoading = true
    /// The list is what was saved, because the last refresh did not land.
    private(set) var isStale = false
    private(set) var error: APIError?

    private let app: AppModel
    private static let cacheKey = "bookings-recent"

    init(app: AppModel) {
        self.app = app
        // What was saved first, so a passenger in a dead spot sees her
        // journeys the moment home opens.
        if let saved = app.personal.value(BookingPage.self, key: Self.cacheKey) {
            bookings = saved.bookings
            isLoading = false
        }
    }

    func refresh() async {
        async let journeys: Void = refreshBookings()
        async let ask: Void = refreshOpenRequest()
        _ = await (journeys, ask)
    }

    /// Keeps the open-request card honest: offers arrive and the request
    /// expires on its own, so a card rendered once is wrong within a minute.
    func poll() async {
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(10))
            if Task.isCancelled { return }
            await refreshOpenRequest()
        }
    }

    private func refreshBookings() async {
        let result = await app.client.send(API.bookings(scope: "all", limit: 20), caching: Self.cacheKey, in: app.personal)
        if let page = result.value { bookings = page.bookings }
        isLoading = false
        isStale = result.isStale
        // A failure with nothing saved is the only screen she has, so it is
        // an error she can act on -- never "no bookings yet", which would be
        // a claim about her journeys the app had not managed to check.
        error = result.error == .cancelled ? error : result.error
    }

    private func refreshOpenRequest() async {
        // A failure leaves the card as it was: the request has not gone away
        // because the network did.
        guard case .success(let mine) = await app.client.send(API.myRideRequests()) else { return }
        openRequest = mine.first(where: \.isOpen)
    }
}
