import XCTest

/// Sign in end to end, against the API on this Mac (`make api`).
///
/// The development server echoes the code in its response and the app fills
/// it in, so no message is sent and no number is paid for. The number is in
/// the reserved +93 700 000 xxx range the backend's own tests use.
@MainActor
final class SignInFlowTests: XCTestCase {
    private let testPhone = "+93700000800"

    override func setUp() async throws {
        continueAfterFailure = false
    }

    func testSigningInLandsOnHome() {
        let app = XCUIApplication()
        app.launchArguments = ["--uitest-fresh"]
        app.launch()
        snapshot("1-sign-in")

        // The same screen in the other two languages: Pashto right to left
        // in Vazirmatn, English left to right in the system face.
        XCTAssertTrue(app.buttons["پښتو"].waitForExistence(timeout: 15))
        app.buttons["پښتو"].tap()
        snapshot("1b-pashto")
        app.buttons["English"].tap()
        snapshot("1c-english")
        app.buttons["دری"].tap()

        let phone = app.textFields["signin.phone"]
        XCTAssertTrue(phone.waitForExistence(timeout: 15))
        phone.tap()
        phone.typeText(testPhone)
        app.buttons["signin.send"].tap()

        let code = app.textFields["signin.code"]
        XCTAssertTrue(code.waitForExistence(timeout: 15), "the code step never appeared -- is `make api` running?")
        XCTAssertGreaterThanOrEqual((code.value as? String)?.count ?? 0, 4, "the echoed code was not filled in")
        snapshot("2-code")

        app.buttons["signin.submit"].tap()

        XCTAssertTrue(app.buttons["home.search"].waitForExistence(timeout: 15)
                      || app.buttons["home.offers"].waitForExistence(timeout: 5))
        snapshot("3-home")
    }
}
