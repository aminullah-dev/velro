import Foundation

/// A client-made key for every mutation that must not happen twice.
///
/// Built from the operation, its inputs and an attempt id the screen holds, so
/// a retry of the same action after a dropped connection reuses the key and
/// gets the original answer, while a genuinely new action gets a new one. The
/// shapes match the Android app's exactly: the server keys on them.
public enum IdempotencyKeys {
    public static func booking(tripId: String, seats: Int, stationId: String, attemptId: String) -> String {
        "booking:\(tripId):\(seats):\(stationId):\(attemptId)"
    }

    /// One accept per attempt, bound to the offer. The offer id alone is not a
    /// key: it is printed on the driver's screen, and a key another account can
    /// name is one another account can try (ADR 0013).
    public static func acceptOffer(offerId: String, attemptId: String) -> String {
        "accept_offer:\(offerId):\(attemptId)"
    }

    /// One ask per attempt: the same journey, seats and attempt replay as one
    /// request instead of ringing every online driver a second time.
    public static func ask(originStationId: String, destinationId: String, seats: Int, attemptId: String) -> String {
        "ask:\(originStationId):\(destinationId):\(seats):\(attemptId)"
    }

    /// Held by the screen for as long as it is the same attempt.
    public static func newAttemptId() -> String { UUID().uuidString.lowercased() }
}
