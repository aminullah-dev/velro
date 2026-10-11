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
        giveNameIfAsked(app)
        XCTAssertTrue(app.buttons["home.search"].waitForExistence(timeout: 15))
        return app
    }

    /// A new account is asked for a first and a last name before home; an
    /// account that already has both goes straight past.
    func giveNameIfAsked(_ app: XCUIApplication, first: String = "مریم", last: String = "احمدی") {
        let field = app.textFields["name.first"]
        guard field.waitForExistence(timeout: 6) else { return }
        field.tap()
        field.typeText(first)
        let lastField = app.textFields["name.last"]
        lastField.tap()
        lastField.typeText(last)
        app.buttons["name.continue"].tap()
    }

    /// Empties a text field, whatever was in it.
    func clear(_ field: XCUIElement) {
        field.tap()
        let length = (field.value as? String)?.count ?? 0
        field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: length + 2))
    }

    /// The first button whose identifier starts with `prefix`: "ask.district"
    /// is any district, "ask.district.GRB-SYG" is Siahgird.
    func tapFirst(_ app: XCUIApplication, _ prefix: String, timeout: TimeInterval = 10) {
        let element = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", prefix)).firstMatch
        XCTAssertTrue(element.waitForExistence(timeout: timeout), "no \(prefix)")
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
