import XCTest

/// Asking for a ride end to end: district, village, station, destination, a
/// price for tomorrow morning; a driver answers; she takes his price, gets a
/// boarding code, and cancels -- which also frees the seeded driver for the
/// next run.
@MainActor
final class AskFlowTests: XCTestCase {
    override func setUp() async throws {
        continueAfterFailure = false
    }

    func testAskTakeAPriceAndBoard() async throws {
        let app = launchSignedIn(phone: freshTestPhone())
        app.buttons["home.search"].tap()

        tapFirst(app, "ask.district")
        tapFirst(app, "ask.village")
        settle()
        snapshot("4-villages")
        // A village with one station skips the station step.
        if app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'ask.station'")).firstMatch.waitForExistence(timeout: 3) {
            tapFirst(app, "ask.station")
        }
        tapFirst(app, "ask.destination.", timeout: 15)
        if app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'ask.destination.child'")).firstMatch.waitForExistence(timeout: 2) {
            tapFirst(app, "ask.destination.child")
        }

        let fare = app.textFields["ask.fare"]
        XCTAssertTrue(fare.waitForExistence(timeout: 10))
        fare.tap()
        fare.typeText("300")
        tapFirst(app, "ask.day.1")
        snapshot("5-ask")

        app.swipeUp()
        let send = app.buttons["ask.send"]
        XCTAssertTrue(send.waitForExistence(timeout: 5))
        XCTAssertTrue(send.isEnabled)
        send.tap()
        allowLocationIfAsked()

        // Waiting for drivers.
        let waiting = app.descendants(matching: .any).matching(identifier: "offers.waiting").firstMatch
        XCTAssertTrue(waiting.waitForExistence(timeout: 20), "the ask never reached the offers screen")
        settle()
        snapshot("6-waiting")

        // A driver names 350 against the 300 she asked.
        let driver = LocalDriver()
        let token = try await driver.signIn()
        try await driver.releaseCurrentTrip(token: token)
        try await driver.offerOnNewestRequest(token: token, amountMinor: 35_000)

        let accept = app.buttons["offers.accept"].firstMatch
        XCTAssertTrue(accept.waitForExistence(timeout: 20), "the offer never reached the screen")
        settle()
        snapshot("7-offer")
        accept.tap()

        // The journey exists: the code she shows the driver.
        XCTAssertTrue(app.staticTexts["booking.code"].waitForExistence(timeout: 20))
        settle()
        snapshot("8-booking")

        // And the help door, on a live journey.
        app.buttons["booking.help"].tap()
        XCTAssertTrue(app.buttons["help.call"].firstMatch.waitForExistence(timeout: 5))
        snapshot("9-help")
        app.swipeDown(velocity: .fast)

        // Cancel, which releases the driver for the next run.
        let cancel = app.buttons["booking.cancel"]
        if !cancel.waitForExistence(timeout: 3) { app.swipeUp() }
        XCTAssertTrue(cancel.waitForExistence(timeout: 5))
        cancel.tap()
        let confirm = app.buttons["booking.cancel.confirm"].firstMatch
        XCTAssertTrue(confirm.waitForExistence(timeout: 5))
        confirm.tap()
        let gone = expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: app.staticTexts["booking.code"])
        await fulfillment(of: [gone], timeout: 20)
        snapshot("10-cancelled")
    }

    /// Lets an animation finish before a screenshot.
    private func settle() { Thread.sleep(forTimeInterval: 0.8) }
}
