import Foundation
import Testing
@testable import VelroCore

@Suite struct AskFormTests {
    @Test func aPriceIsWholeAfghaniTypedInEitherDigits() {
        var form = AskForm(nowHour: 9)
        form.offeredFare = "۳۰۰"
        #expect(form.offeredFare == "300")
        #expect(form.fareMinor == 30_000)
        form.offeredFare = "0"
        #expect(form.fareMinor == nil)
        #expect(!form.isComplete)
    }

    /// Six in the evening, "today": the hours on offer are 19 and 20, and the
    /// chosen one moves with them rather than staying at six in the morning.
    @Test func todayInTheEveningOffersOnlyWhatIsLeft() {
        var form = AskForm(nowHour: 18)
        form.offeredFare = "300"
        form.setDeparture(day: 0, hour: form.departureHour)
        #expect(form.departureHours == [19, 20])
        #expect(form.departureHour == 19)
        #expect(form.isComplete)
    }

    @Test func aSpentDayCannotBeAskedFor() {
        var form = AskForm(nowHour: 21)
        form.offeredFare = "300"
        form.setDeparture(day: 0, hour: 6)
        #expect(form.departureHours.isEmpty)
        #expect(!form.isComplete)
    }

    @Test func aRoundTripNeedsBothPrices() {
        var form = AskForm(nowHour: 9)
        form.offeredFare = "300"
        form.setDeparture(day: 1, hour: 6)
        form.setReturn(afterDays: 1, hour: 14)
        #expect(form.totalFareMinor == nil)
        #expect(!form.isComplete)
        form.returnFare = "250"
        #expect(form.totalFareMinor == 55_000)
        #expect(form.isComplete)
    }

    /// A same-day return leaves after the outbound, and moving the outbound
    /// later drags the return with it.
    @Test func aSameDayReturnStaysAfterTheOutbound() {
        var form = AskForm(nowHour: 9)
        form.setDeparture(day: 1, hour: 6)
        form.setReturn(afterDays: 0, hour: 14)
        form.setDeparture(day: 1, hour: 18)
        #expect(form.returnHours == [19, 20])
        #expect(form.returnHour == 19)
    }

    @Test func nowTakesTheReturnWithIt() {
        var form = AskForm(nowHour: 9)
        form.setDeparture(day: 1, hour: 6)
        form.setReturn(afterDays: 2, hour: 14)
        form.setDeparture(day: nil, hour: 6)
        #expect(form.returnFor() == nil)
        #expect(form.requestedFor() == nil)
    }

    @Test func timesAreSentInKabulTime() {
        let now = ISODate.parse("2026-09-10T10:00:00Z")!
        var form = AskForm(nowHour: Calendars.kabulHour(now))
        form.setDeparture(day: 1, hour: 6)
        form.setReturn(afterDays: 1, hour: 14)
        #expect(ISODate.format(form.requestedFor(now: now)!) == "2026-09-11T01:30:00Z")
        #expect(ISODate.format(form.returnFor(now: now)!) == "2026-09-12T09:30:00Z")
    }

    @Test func steppingBackClearsTheAnswers() {
        var form = AskForm(nowHour: 9)
        form.offeredFare = "300"
        form.note = "two bags"
        form.setDeparture(day: 1, hour: 6)
        form.setReturn(afterDays: 1, hour: 14)
        form.clearAnswers()
        #expect(form.offeredFare.isEmpty && form.note.isEmpty && form.returnFor() == nil)
    }
}
