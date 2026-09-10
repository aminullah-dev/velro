import XCTest

/// Shared steps for the flows that start signed in.
@MainActor
extension XCTestCase {
    /// A number in the reserved +93 700 000 xxx range, fresh for the run, so an
    /// ask left open by an earlier run cannot refuse this one's.
    func freshTestPhone() -> String {
        String(format: "+93700000%03d", Int.random(in: 810...989))
    }

    /// Launches signed out, in Dari, and signs in with the code the development
    /// server echoes back. No message is sent.
    func launchSignedIn(phone: String) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-fresh"]
        app.launch()
        let field = app.textFields["signin.phone"]
        XCTAssertTrue(field.waitForExistence(timeout: 15))
        field.tap()
        field.typeText(phone)
        app.buttons["signin.send"].tap()
        XCTAssertTrue(app.textFields["signin.code"].waitForExistence(timeout: 15), "is `make api` running?")
        app.buttons["signin.submit"].tap()
        XCTAssertTrue(app.buttons["home.search"].waitForExistence(timeout: 15))
        return app
    }

    func tapFirst(_ app: XCUIApplication, _ identifier: String, timeout: TimeInterval = 10) {
        let element = app.buttons.matching(identifier: identifier).firstMatch
        XCTAssertTrue(element.waitForExistence(timeout: timeout), "no \(identifier)")
        element.tap()
    }

    /// iOS's own location prompt, answered the way a passenger would.
    func allowLocationIfAsked() {
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        for label in ["Allow While Using App", "Allow Once"] {
            let button = springboard.buttons[label]
            if button.waitForExistence(timeout: 3) {
                button.tap()
                return
            }
        }
    }

    func snapshot(_ name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
