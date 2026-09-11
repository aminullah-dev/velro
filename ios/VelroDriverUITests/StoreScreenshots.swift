import XCTest

/// The App Store's pictures of VELRO Driver, taken from the real app on a real
/// trip against `make api`, in Dari, the language it opens in.
///
/// Not part of the ordinary run: `make store-shots APP=driver` sets
/// VELRO_STORE_SHOTS, a 9:41 status bar and a position on the Siahgird road,
/// then copies the pictures into ios/AppStore/driver/screenshots.
@MainActor
final class StoreScreenshots: XCTestCase {
    private let seededDriver = "+93700000020"

    override func setUp() async throws {
        continueAfterFailure = false
        try XCTSkipUnless(ProcessInfo.processInfo.environment["VELRO_STORE_SHOTS"] == "1", "store screenshots only on request")
    }

    /// A moment for the screen to settle: animations, a poll, a map tile.
    private func pause(_ seconds: TimeInterval) {
        RunLoop.current.run(until: Date.now.addingTimeInterval(seconds))
    }

    private func shot(_ name: String) {
        RunLoop.current.run(until: Date.now.addingTimeInterval(1.5))
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func allowSystemAlerts() {
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        for label in ["Allow While Using App", "Allow"] where springboard.buttons[label].waitForExistence(timeout: 2) {
            springboard.buttons[label].tap()
        }
    }

    /// Presses the big button once it has moved on from `previous`.
    @discardableResult
    private func next(_ app: XCUIApplication, after previous: String?) -> String {
        let button = app.buttons["trip.next"]
        let deadline = Date.now.addingTimeInterval(40)
        while Date.now < deadline {
            if button.exists, button.isHittable, button.label != previous { break }
            allowSystemAlerts()
            RunLoop.current.run(until: Date.now.addingTimeInterval(0.5))
        }
        let label = button.label
        XCTAssertNotEqual(label, previous, "the trip did not move on from \(previous ?? "")")
        button.tap()
        return label
    }

    func testStoreScreenshots() async throws {
        try await LocalPassenger.releaseDriver(phone: seededDriver)
        let passenger = LocalPassenger()
        let token = try await passenger.signIn()
        try await passenger.setName("مریم", token: token)
        let requestId = try await passenger.ask(token: token, fareAfghani: 350)

        let app = XCUIApplication()
        app.launchArguments = ["--uitest-fresh"]
        app.launch()
        let phone = app.textFields["signin.phone"]
        XCTAssertTrue(phone.waitForExistence(timeout: 15))
        phone.tap()
        phone.typeText(seededDriver)
        app.buttons["signin.send"].tap()
        XCTAssertTrue(app.textFields["signin.code"].waitForExistence(timeout: 15))
        app.buttons["signin.submit"].tap()

        let online = app.switches["home.online"]
        XCTAssertTrue(online.waitForExistence(timeout: 20))
        if (online.value as? String) != "1" { online.tap() }
        allowSystemAlerts()
        let board = app.buttons["home.board"]
        XCTAssertTrue(board.waitForExistence(timeout: 20))
        shot("01-home")

        board.tap()
        let offer = app.buttons["board.offer.\(requestId)"]
        XCTAssertTrue(offer.waitForExistence(timeout: 20))
        shot("02-board")
        offer.tap()
        XCTAssertTrue(app.buttons["offer.match"].waitForExistence(timeout: 10))
        shot("03-offer")
        app.buttons["offer.match"].tap()
        pause(2)

        let code = try await passenger.acceptFirstOffer(token: token, requestId: requestId)
        app.navigationBars.buttons.firstMatch.tap()

        var label = next(app, after: nil)                       // on my way
        let read = app.buttons["home.inbox.read"]
        if read.waitForExistence(timeout: 5) { read.tap() }
        pause(3)
        // A slow drag with a hold at the end, so the list stops where the
        // finger does: the trip card and its map, not the earnings below.
        let start = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.75))
        start.press(forDuration: 0.3, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.47)),
                    withVelocity: .slow, thenHoldForDuration: 0.5)
        pause(4)
        shot("04-trip")
        app.swipeDown()
        label = next(app, after: label)                         // arrived
        let field = app.textFields["trip.code"]
        XCTAssertTrue(field.waitForExistence(timeout: 20))
        field.tap()
        field.typeText(code)
        app.buttons["trip.verify"].tap()
        pause(3)
        label = next(app, after: label)                         // boarding
        label = next(app, after: label)                         // start the trip
        XCTAssertTrue(app.buttons["ride.help"].waitForExistence(timeout: 20))
        pause(4)
        shot("05-ride-map")
        label = next(app, after: label)                         // arrived at destination
        next(app, after: label)                                 // complete

        XCTAssertTrue(online.waitForExistence(timeout: 20))
        pause(5)
        let earnings = app.buttons["home.earnings"]
        for _ in 0..<4 where !earnings.isHittable { app.swipeUp() }
        earnings.tap()
        pause(3)
        shot("06-earnings")
        app.navigationBars.buttons.firstMatch.tap()
        for _ in 0..<4 { app.swipeDown() }
        app.buttons.matching(NSPredicate(format: "label == %@", "اسناد شما")).firstMatch.tap()
        pause(3)
        shot("07-documents")
    }
}
