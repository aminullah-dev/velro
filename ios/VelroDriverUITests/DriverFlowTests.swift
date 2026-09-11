import XCTest

/// The driver app, end to end against the API on this Mac (`make api`).
///
/// +93700000020 is the development seed's approved driver with an active car
/// (`Toyota Corolla`, PRW-1234). The server echoes the sign-in code, so no
/// message is sent.
@MainActor
final class DriverFlowTests: XCTestCase {
    private let seededDriver = "+93700000020"

    override func setUp() async throws {
        continueAfterFailure = false
    }

    private func launchSignedIn(phone: String) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-fresh"]
        app.launch()
        XCTAssertTrue(app.buttons["English"].waitForExistence(timeout: 15))
        app.buttons["English"].tap()
        let field = app.textFields["signin.phone"]
        XCTAssertTrue(field.waitForExistence(timeout: 15))
        field.tap()
        field.typeText(phone)
        app.buttons["signin.send"].tap()
        XCTAssertTrue(app.textFields["signin.code"].waitForExistence(timeout: 15), "is `make api` running?")
        app.buttons["signin.submit"].tap()
        return app
    }

    private func snapshot(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    /// Signed in, the approved driver sees his car and the switch; going
    /// online shows the passengers waiting, and the board opens from there.
    func testAnApprovedDriverGoesOnlineAndSeesTheBoard() {
        let app = launchSignedIn(phone: seededDriver)
        let online = app.switches["home.online"]
        XCTAssertTrue(online.waitForExistence(timeout: 20), "the approved driver's switch never appeared")
        snapshot("1-home")
        if (online.value as? String) != "1" {
            online.switches.firstMatch.exists ? online.switches.firstMatch.tap() : online.tap()
        }
        let board = app.buttons["home.board"]
        let empty = app.staticTexts["Nobody is waiting right now."]
        XCTAssertTrue(board.waitForExistence(timeout: 15) || empty.waitForExistence(timeout: 1))
        snapshot("2-online")
        if board.exists {
            board.tap()
            XCTAssertTrue(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "board.offer.")).firstMatch.waitForExistence(timeout: 15)
                          || app.staticTexts["Nobody is waiting right now."].exists)
            snapshot("3-board")
        }
    }

    /// iOS's own prompts -- notifications when he goes online, location when
    /// a trip is his -- answered the way a driver would.
    private func allowSystemAlerts() {
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        for _ in 0..<3 {
            var answered = false
            for label in ["Allow While Using App", "Allow"] {
                let button = springboard.buttons[label]
                if button.waitForExistence(timeout: 2) {
                    button.tap()
                    answered = true
                    break
                }
            }
            if !answered { return }
        }
    }

    /// Waits for the big button to say `label`, then presses it.
    private func step(_ app: XCUIApplication, _ label: String, timeout: TimeInterval = 30) {
        let next = app.buttons["trip.next"]
        let deadline = Date.now.addingTimeInterval(timeout)
        while Date.now < deadline {
            if next.exists, next.label == label, next.isHittable { break }
            allowSystemAlerts()
            RunLoop.current.run(until: Date.now.addingTimeInterval(0.5))
        }
        XCTAssertEqual(next.label, label, "the next step never read \(label)")
        next.tap()
    }

    /// The whole trip, from his side: a passenger (played through the API)
    /// asks, he agrees to her price on the board, she accepts, and he takes
    /// every step -- on my way, arrived, her code, boarding, the ride map,
    /// arrival, complete.
    func testAFullTripFromTheDriversSide() async throws {
        try await LocalPassenger.releaseDriver(phone: seededDriver)
        let passenger = LocalPassenger()
        let token = try await passenger.signIn()
        let fare = Int.random(in: 610...690)
        let requestId = try await passenger.ask(token: token, fareAfghani: fare)

        let app = launchSignedIn(phone: seededDriver)
        let online = app.switches["home.online"]
        XCTAssertTrue(online.waitForExistence(timeout: 20))
        if (online.value as? String) != "1" { online.tap() }
        allowSystemAlerts()
        let board = app.buttons["home.board"]
        XCTAssertTrue(board.waitForExistence(timeout: 20), "her request never reached the home screen")
        board.tap()

        let offer = app.buttons["board.offer.\(requestId)"]
        XCTAssertTrue(offer.waitForExistence(timeout: 20), "her request is not on the board")
        offer.tap()
        let match = app.buttons["offer.match"]
        XCTAssertTrue(match.waitForExistence(timeout: 10))
        snapshot("4-offer-sheet")
        match.tap()
        XCTAssertTrue(app.staticTexts["You offered \(fare) AFN"].waitForExistence(timeout: 15))
        snapshot("5-offered")

        let code = try await passenger.acceptFirstOffer(token: token, requestId: requestId)
        app.navigationBars.buttons.firstMatch.tap()

        step(app, "On my way")
        snapshot("6-trip")
        step(app, "I have arrived")
        let field = app.textFields["trip.code"]
        XCTAssertTrue(field.waitForExistence(timeout: 20))
        field.tap()
        field.typeText(code)
        app.buttons["trip.verify"].tap()
        XCTAssertTrue(app.staticTexts["Passenger verified. They are on board."].waitForExistence(timeout: 20)
                      || app.staticTexts.matching(NSPredicate(format: "label ENDSWITH %@", "is on board.")).firstMatch.waitForExistence(timeout: 5))
        snapshot("7-verified")
        step(app, "Start boarding")
        step(app, "Start trip")
        XCTAssertTrue(app.buttons["ride.help"].waitForExistence(timeout: 20), "the ride map never came up")
        snapshot("8-ride-map")
        step(app, "Arrived at destination")
        step(app, "Complete trip")
        XCTAssertTrue(app.switches["home.online"].waitForExistence(timeout: 20))
        snapshot("9-done")
    }

    /// Somebody who has never driven signs in and is offered the way in.
    func testANewPersonIsOfferedTheApplication() {
        let phone = String(format: "+93700000%03d", Int.random(in: 810...989))
        let app = launchSignedIn(phone: phone)
        let apply = app.buttons["home.apply"]
        XCTAssertTrue(apply.waitForExistence(timeout: 20))
        snapshot("1-welcome")
        apply.tap()
        XCTAssertTrue(app.buttons["apply.submit"].waitForExistence(timeout: 15))
        snapshot("2-apply")
    }
}
