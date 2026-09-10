import XCTest

/// Her account, her journeys, and a report to VELRO -- the screens around the
/// ride itself.
@MainActor
final class AccountFlowTests: XCTestCase {
    override func setUp() async throws {
        continueAfterFailure = false
    }

    /// A name added, the language changed and changed back, then signing out.
    func testNameLanguageAndSigningOut() {
        let app = launchSignedIn(phone: freshTestPhone())
        app.buttons["home.account"].tap()

        let name = app.textFields["account.name"]
        XCTAssertTrue(name.waitForExistence(timeout: 10))
        name.tap()
        name.typeText("مریم")
        app.buttons.matching(identifier: "account.name").firstMatch.exists ? () : ()
        app.swipeUp()
        snapshot("11-account")

        // English, then back to Dari: the one way out of a language she cannot read.
        app.buttons["English"].tap()
        XCTAssertTrue(app.navigationBars["Your account"].waitForExistence(timeout: 5))
        snapshot("12-account-english")
        app.buttons["دری"].tap()
        XCTAssertTrue(app.navigationBars["حساب شما"].waitForExistence(timeout: 5))

        let signOut = app.buttons["account.signout"]
        if !signOut.isHittable { app.swipeUp() }
        signOut.tap()
        let confirm = app.buttons["account.signout.confirm"].firstMatch
        XCTAssertTrue(confirm.waitForExistence(timeout: 5))
        confirm.tap()
        XCTAssertTrue(app.textFields["signin.phone"].waitForExistence(timeout: 10))
    }

    /// From home's help door: a report with a reference she keeps, then the
    /// list where VELRO's answer will arrive, then her journeys.
    func testReportingAndHistory() {
        let app = launchSignedIn(phone: freshTestPhone())
        app.buttons["home.help"].tap()
        XCTAssertTrue(app.buttons["help.call"].firstMatch.waitForExistence(timeout: 5))
        snapshot("13-help-home")

        app.swipeUp()
        app.buttons["help.report"].tap()
        let category = app.buttons["report.category.APP_PROBLEM"]
        XCTAssertTrue(category.waitForExistence(timeout: 5))
        category.tap()
        let text = app.textViews["report.text"]
        text.tap()
        text.typeText("The map did not load at the station.")
        app.swipeUp()
        app.buttons["report.submit"].tap()
        XCTAssertTrue(app.staticTexts["report.reference"].waitForExistence(timeout: 15))
        snapshot("14-report-sent")

        // Close the form, then open the list of her reports.
        app.buttons["report.close"].tap()
        app.swipeUp()
        let reports = app.buttons["help.reports"]
        XCTAssertTrue(reports.waitForExistence(timeout: 5))
        reports.tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'TKT'")).firstMatch.waitForExistence(timeout: 10))
        snapshot("15-reports")

        // Back home, then her journeys.
        app.navigationBars.buttons.firstMatch.tap()
        let history = app.buttons["home.history"]
        XCTAssertTrue(history.waitForExistence(timeout: 5))
        history.tap()
        XCTAssertTrue(app.segmentedControls.firstMatch.waitForExistence(timeout: 5))
        app.segmentedControls.buttons["گذشته"].tap()
        Thread.sleep(forTimeInterval: 1)
        snapshot("16-history-past")
    }
}
