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
            XCTAssertTrue(app.buttons.matching(identifier: "board.offer").firstMatch.waitForExistence(timeout: 15)
                          || app.staticTexts["Nobody is waiting right now."].exists)
            snapshot("3-board")
        }
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
