import Foundation

/// The answers on the ask step, section 89: a price, how many, and when.
///
/// A value with no screen and no network, so the rules that have gone wrong
/// before -- hours offered that the server then refuses, a round trip priced
/// on one leg, a return left behind by a moved departure -- are checked in a
/// unit test rather than found at a roadside. The rules are the Android
/// `BookingFlowUiState`'s.
public struct AskForm: Sendable, Equatable {
    /// Cars out of Ghorband leave early, and nothing sensible leaves at two in
    /// the morning: sixteen hours are offered, not twenty-four to scroll.
    public static let earliestHour = 4
    public static let latestHour = 20
    public static let defaultDepartureHour = 6
    /// Coming back is an afternoon thing far more often than a dawn one.
    public static let defaultReturnHour = 14

    /// What the passenger will pay, in whole afghani as typed.
    public var offeredFare = "" { didSet { offeredFare = Self.digits(offeredFare) } }
    /// The return leg's price, when there is a return.
    public var returnFare = "" { didSet { returnFare = Self.digits(returnFare) } }
    public var note = ""
    public var passengers = 1 { didSet { passengers = min(4, max(1, passengers)) } }

    /// nil is now; 0 today, 1 tomorrow, 2 the day after. Days and an hour
    /// rather than a date picker: "tomorrow morning" is how these journeys are
    /// arranged, by people who may not read well, at a roadside.
    public private(set) var departureDay: Int?
    public private(set) var departureHour = AskForm.defaultDepartureHour
    /// Days after the departure to come back, or nil for one way.
    public private(set) var returnAfterDays: Int?
    public private(set) var returnHour = AskForm.defaultReturnHour
    /// The hour it is in Kabul, held here so the rules can be tested at six
    /// in the evening without waiting for six in the evening.
    public var nowHour: Int

    public init(nowHour: Int) {
        self.nowHour = nowHour
    }

    // MARK: Prices

    public var fareMinor: Int64? { Self.minor(offeredFare) }

    public var returnFareMinor: Int64? { returnAfterDays == nil ? nil : Self.minor(returnFare) }

    /// Both legs together, and nil until every chosen leg has a price: an
    /// unpriced return counted as zero once showed a total the passenger
    /// might well have sent.
    public var totalFareMinor: Int64? {
        guard let out = fareMinor else { return nil }
        if returnAfterDays != nil {
            guard let back = returnFareMinor else { return nil }
            return out + back
        }
        return out
    }

    // MARK: Hours

    /// Today's hours start after the current one: offering four in the
    /// morning at six in the evening invites a choice the server refuses.
    public var departureHours: [Int] {
        let first = departureDay == 0 ? max(Self.earliestHour, nowHour + 1) : Self.earliestHour
        return first <= Self.latestHour ? Array(first...Self.latestHour) : []
    }

    /// A same-day return leaves after the outbound does.
    public var returnHours: [Int] {
        let first = returnAfterDays == 0 ? departureHour + 1 : Self.earliestHour
        let start = max(first, Self.earliestHour)
        return start <= Self.latestHour ? Array(start...Self.latestHour) : []
    }

    /// Choose when. Moving the outbound to "now" takes the return with it --
    /// "back two days after" means nothing with no day to count from -- and
    /// both hours are pulled back inside what is offered.
    ///
    /// Android only re-clamps when a destination is chosen, so tapping
    /// "today" at six in the evening there leaves the six-o'clock default
    /// selected under a row showing 19:00 and 20:00, and the ask is refused
    /// for a time in the past. Here every change is clamped.
    public mutating func setDeparture(day: Int?, hour: Int) {
        departureDay = day
        departureHour = hour
        if day == nil { returnAfterDays = nil }
        clampHours()
    }

    public mutating func setReturn(afterDays: Int?, hour: Int) {
        returnAfterDays = departureDay == nil ? nil : afterDays
        returnHour = hour
        clampHours()
    }

    public mutating func clampHours() {
        if let first = departureHours.first, !departureHours.contains(departureHour) { departureHour = first }
        if let first = returnHours.first, !returnHours.contains(returnHour) { returnHour = first }
    }

    /// When the journey is for, in Kabul time; nil for now.
    public func requestedFor(now: Date = .now) -> Date? {
        guard let day = departureDay else { return nil }
        return Calendars.kabul(daysFromToday: day, hour: departureHour, now: now)
    }

    /// The way back; nil for one way, and always nil with no departure day.
    public func returnFor(now: Date = .now) -> Date? {
        guard let day = departureDay, let after = returnAfterDays else { return nil }
        return Calendars.kabul(daysFromToday: day + after, hour: returnHour, now: now)
    }

    /// Complete enough to send. A chosen return with no price is unfinished,
    /// not one way: the server needs both legs or neither. A day with no hours
    /// left on it cannot be asked for.
    public var isComplete: Bool {
        fareMinor != nil
            && (returnAfterDays == nil || returnFareMinor != nil)
            && (departureDay == nil || !departureHours.isEmpty)
            && (returnAfterDays == nil || !returnHours.isEmpty)
    }

    /// Stepping back from the ask clears its answers: a price typed for one
    /// destination must not silently become the offer for another.
    public mutating func clearAnswers() {
        offeredFare = ""
        note = ""
        returnFare = ""
        returnAfterDays = nil
    }

    private static func digits(_ text: String) -> String {
        String(Numerals.latin(text).filter(\.isASCII).filter(\.isNumber).prefix(7))
    }

    private static func minor(_ text: String) -> Int64? {
        guard let whole = Int64(text), whole > 0 else { return nil }
        return whole * 100
    }
}
