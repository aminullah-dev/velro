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

    /// Leaving for good: what goes and what stays, one question, and the phone
    /// lands on sign-in saying so. The same number then comes back as somebody
    /// new -- without the name the old account had.
    func testDeletingTheAccount() {
        let phone = freshTestPhone()
        let app = launchSignedIn(phone: phone)
        app.buttons["home.account"].tap()

        let name = app.textFields["account.name"]
        XCTAssertTrue(name.waitForExistence(timeout: 10))
        name.tap()
        name.typeText("زهره")
        app.buttons["account.name.save"].tap()
        Thread.sleep(forTimeInterval: 1)

        let delete = app.buttons["account.delete"]
        while !delete.isHittable { app.swipeUp() }
        snapshot("17-account-doors")
        delete.tap()

        let start = app.buttons["account.delete.start"]
        XCTAssertTrue(start.waitForExistence(timeout: 5))
        snapshot("18-delete-account")
        start.tap()
        let confirm = app.alerts.buttons["حسابم را حذف کن"].firstMatch
        XCTAssertTrue(confirm.waitForExistence(timeout: 5))
        snapshot("19-delete-confirm")
        confirm.tap()

        XCTAssertTrue(app.textFields["signin.phone"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.staticTexts["signin.account_deleted"].exists || app.otherElements["signin.account_deleted"].exists)
        snapshot("20-deleted")

        // The same number again: a fresh account, not the old one.
        let field = app.textFields["signin.phone"]
        field.tap()
        field.typeText(phone)
        app.buttons["signin.send"].tap()
        XCTAssertTrue(app.textFields["signin.code"].waitForExistence(timeout: 15))
        app.buttons["signin.submit"].tap()
        XCTAssertTrue(app.buttons["home.account"].waitForExistence(timeout: 15))
        app.buttons["home.account"].tap()
        let again = app.textFields["account.name"]
        XCTAssertTrue(again.waitForExistence(timeout: 10))
        XCTAssertFalse((again.value as? String ?? "").contains("زهره"))
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
