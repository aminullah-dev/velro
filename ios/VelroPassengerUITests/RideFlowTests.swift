import XCTest

/// The ride itself: from the moment the driver starts the trip, the
/// passenger's phone shows the full-screen ride map on its own -- the road's
/// next warning at the top, the driver's and her name at the foot -- and
/// hands back to the booking when the ride ends.
///
/// Khishki to Charikar, the journey whose two ends have coordinates, so the
/// road is drawn and its warnings can be named.
@MainActor
final class RideFlowTests: XCTestCase {
    override func setUp() async throws {
        continueAfterFailure = false
    }

    func testStartingTheTripOpensTheRideMapOnHerPhone() async throws {
        let app = launchSignedIn(phone: freshTestPhone())
        app.buttons["home.search"].tap()
        tapFirst(app, "ask.district.GRB-SYG", timeout: 15)
        let filter = app.textFields["ask.filter"]
        XCTAssertTrue(filter.waitForExistence(timeout: 10))
        filter.tap()
        filter.typeText("خیشکی")
        tapFirst(app, "ask.village")
        if app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'ask.station'")).firstMatch.waitForExistence(timeout: 3) {
            tapFirst(app, "ask.station")
        }
        tapFirst(app, "ask.destination.EXT-CHK", timeout: 15)

        let fare = app.textFields["ask.fare"]
        XCTAssertTrue(fare.waitForExistence(timeout: 10))
        fare.tap()
        fare.typeText("400")
        app.swipeUp()
        app.buttons["ask.send"].tap()
        allowLocationIfAsked()

        let driver = LocalDriver()
        let token = try await driver.signIn()
        try await driver.releaseCurrentTrip(token: token)
        let waiting = app.descendants(matching: .any).matching(identifier: "offers.waiting").firstMatch
        XCTAssertTrue(waiting.waitForExistence(timeout: 20))
        try await driver.offerOnNewestRequest(token: token, amountMinor: 40_000)

        let accept = app.buttons["offers.accept"].firstMatch
        XCTAssertTrue(accept.waitForExistence(timeout: 20))
        accept.tap()
        let code = app.staticTexts["booking.code"]
        XCTAssertTrue(code.waitForExistence(timeout: 20))

        // The driver's side, step by step, as his big button walks it.
        let trip = try await driver.currentTrip(token: token)
        try await driver.advance(token: token, tripId: trip.id, to: "DRIVER_ARRIVING")
        try await driver.advance(token: token, tripId: trip.id, to: "ARRIVED_AT_PICKUP")
        try await driver.advance(token: token, tripId: trip.id, to: "BOARDING")
        try await driver.verify(token: token, tripId: trip.id, code: code.label)
        if let origin = trip.origin { try await driver.ping(token: token, at: origin) }
        try await driver.advance(token: token, tripId: trip.id, to: "IN_TRANSIT")

        // Her phone, on its own: the ride map, with who is in the car.
        let names = app.descendants(matching: .any).matching(identifier: "ride.names").firstMatch
        XCTAssertTrue(names.waitForExistence(timeout: 20), "the ride map did not open when the trip started")
        try await Task.sleep(for: .seconds(3))
        snapshot("17-ride-map")

        // Arrival hands her back to the booking, where the rating is.
        try await driver.advance(token: token, tripId: trip.id, to: "ARRIVED")
        try await driver.advance(token: token, tripId: trip.id, to: "COMPLETED")
        let gone = expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: names)
        await fulfillment(of: [gone], timeout: 30)
        try await Task.sleep(for: .seconds(1))
        snapshot("18-after-ride")
    }
}
