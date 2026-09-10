import Foundation
import Observation
import VelroCore

/// One booking, kept current while she looks at it.
///
/// Saved as well as fetched, so a passenger opening it in a valley with no
/// signal still sees her seat, her code and where she is going -- which is
/// the whole point of keeping bookings at all.
@MainActor
@Observable
final class BookingDetailModel {
    private(set) var booking: Booking?
    private(set) var isStale = false
    private(set) var error: APIError?
    private(set) var map: TripMap?
    /// Where the car is, while a car is owed to this booking.
    private(set) var vehicle: VehicleLocation?
    private(set) var isCancelling = false
    private(set) var ratingSubmitted = false

    let bookingId: String
    private let app: AppModel
    private var cacheKey: String { "booking-\(bookingId)" }

    init(app: AppModel, bookingId: String) {
        self.app = app
        self.bookingId = bookingId
        booking = app.personal.value(Booking.self, key: cacheKey)
    }

    var canCancel: Bool { booking?.canCancel == true && !isCancelling }
    var canRate: Bool { booking?.canRate == true && !ratingSubmitted }

    /// The code shows while it can still board her, and not on a receipt.
    var showsCode: Bool {
        guard let status = booking?.status else { return false }
        return [.confirmed, .driverAssigned, .ready].contains(status)
    }

    /// Everything on this screen changes without her -- a driver assigned,
    /// arriving, there; the trip called off -- so it is re-read while she
    /// watches, and not at all once the booking is over.
    func poll() async {
        await refresh(asked: true)
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(12))
            if Task.isCancelled { return }
            guard booking?.isActive != false else { return }
            await refresh(asked: false)
        }
    }

    /// `asked` only when she pulled or retried: a background refresh must not
    /// wipe the message from a cancel that failed, or she cannot tell whether
    /// her seat was cancelled at all.
    func refresh(asked: Bool) async {
        if asked { error = nil }
        let result = await app.client.send(API.booking(bookingId), caching: cacheKey, in: app.personal)
        if let fresh = result.value { booking = fresh }
        isStale = result.isStale
        if let failure = result.error, failure != .cancelled, booking == nil || failure != .offline {
            error = failure
        }
        await refreshRoad()
    }

    /// The car's dot, asked for only while a car is owed; any empty or failed
    /// answer simply clears it.
    private func refreshRoad() async {
        guard let booking else { return }
        let trackable: Set<BookingStatus> = [.driverAssigned, .ready, .onboard]
        if map == nil, booking.isActive {
            if case .success(let drawn) = await app.client.send(
                API.journeyMap(originStationId: booking.pickupStationId, destinationId: booking.dropoffDestinationId)
            ) { map = drawn }
        }
        guard trackable.contains(booking.status) else {
            vehicle = nil
            return
        }
        if case .success(let ping) = await app.client.sendNullable(API.vehicleLocation(bookingId)) {
            vehicle = ping
        } else {
            vehicle = nil
        }
    }

    func cancel() async {
        isCancelling = true
        error = nil
        let result = await app.client.send(API.cancelBooking(bookingId))
        isCancelling = false
        switch result {
        case .success: await refresh(asked: false)
        case .failure(let failure): if failure != .cancelled { error = failure }
        }
    }

    func rate(_ score: Int) async {
        guard let tripId = booking?.tripId else { return }
        switch await app.client.send(API.rateTrip(tripId: tripId, bookingId: bookingId, score: score, comment: nil)) {
        case .success:
            ratingSubmitted = true
        case .failure(let failure):
            // Already rated is not worth alarming anybody over.
            if failure.code == "RATING_ALREADY_SUBMITTED" {
                ratingSubmitted = true
            } else if failure != .cancelled {
                error = failure
            }
        }
    }

    /// What the help sheet reads down a phone line.
    var rideFacts: RideFacts? {
        guard let booking else { return nil }
        return RideFacts(
            bookingNumber: booking.number,
            driverName: booking.driverName,
            driverPhone: booking.driverPhone,
            plate: booking.vehiclePlate,
            origin: booking.pickupStationName,
            destination: booking.dropoffDestinationName
        )
    }
}
