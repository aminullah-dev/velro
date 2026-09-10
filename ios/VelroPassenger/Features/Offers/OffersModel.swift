import Foundation
import Observation
import UIKit
import VelroCore

/// Waiting for drivers to name their price, section 89.
///
/// Polls rather than asking to be pulled: nobody refreshes a screen they are
/// standing at a roadside waiting on.
@MainActor
@Observable
final class OffersModel {
    private(set) var request: RideRequest?
    private(set) var isLoading = true
    private(set) var acceptingOfferId: String?
    private(set) var isCancelling = false
    private(set) var error: APIError?
    /// Each bidding driver's face. Fetched after the prices and never waited
    /// on by them; a missing one draws a silhouette -- and also means "not
    /// allowed", which looks the same on screen, and should.
    private(set) var photos: [String: UIImage] = [:]
    /// Set once the journey exists; the screen goes to it.
    private(set) var agreedBookingId: String?
    private(set) var cancelled = false

    /// Held for the whole visit, so a retry of the same Accept after a dropped
    /// connection carries the same key and gets the same journey back -- never
    /// a second one. The server keeps that answer under this passenger alone.
    private let attemptId = IdempotencyKeys.newAttemptId()
    private var photosAsked: Set<String> = []
    private let app: AppModel

    init(app: AppModel) { self.app = app }

    /// Often enough to feel live, rarely enough to spare a data bundle. Stops
    /// the moment there is nothing left to wait for.
    func poll() async {
        await load(asked: true)
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(6))
            if Task.isCancelled || agreedBookingId != nil || cancelled { return }
            if request?.isOpen == false { return }
            if acceptingOfferId != nil { continue }
            await load(asked: false)
        }
    }

    func reload() async { await load(asked: true) }

    private func load(asked: Bool) async {
        if asked { isLoading = request == nil }
        switch await app.client.send(API.myRideRequests()) {
        case .success(let mine):
            // The newest request is the one being waited on.
            request = mine.first
            isLoading = false
            // Cleared only by a reload that was asked for: a background one
            // must not wipe "somebody already took that price" a moment
            // after it appeared, or the failed tap looks like a tap that did
            // nothing and she presses the same driver again.
            if asked { error = nil }
            // Matched with a booking already on it: an accept that worked but
            // whose answer never arrived. She lands on her booking exactly as
            // if the reply had come the first time.
            if let request, !request.isOpen, let booking = request.bookingId {
                agreedBookingId = booking
            }
            loadPhotos()
        case .failure(let failure):
            isLoading = false
            // A failed poll over offers already on screen is not worth a banner.
            if failure != .cancelled && (asked || request == nil) { error = failure }
        }
    }

    func accept(_ offer: FareOffer) async {
        // One action in flight: two taps on a slow connection must not agree
        // two fares.
        guard acceptingOfferId == nil else { return }
        acceptingOfferId = offer.id
        error = nil
        let result = await app.client.send(API.acceptOffer(offer.id, attemptId: attemptId))
        acceptingOfferId = nil
        switch result {
        case .success(let accepted):
            agreedBookingId = accepted.bookingId
        case .failure(let failure):
            if failure != .cancelled { error = failure }
            // Somebody else may have taken it, or the driver withdrawn: read
            // again so the list matches what just happened.
            await load(asked: false)
        }
    }

    func cancel() async {
        guard let request else { return }
        isCancelling = true
        error = nil
        let result = await app.client.send(API.cancelRideRequest(request.id))
        isCancelling = false
        switch result {
        case .success: cancelled = true
        case .failure(let failure): if failure != .cancelled { error = failure }
        }
    }

    /// One fetch per driver not already held: this list polls every few
    /// seconds, and re-fetching a face already on screen spends her data.
    private func loadPhotos() {
        for offer in request?.liveOffers ?? [] where !photosAsked.contains(offer.driverId) {
            photosAsked.insert(offer.driverId)
            let driver = offer.driverId
            Task {
                if case .success(let data) = await app.client.data(API.driverPhoto(driver)),
                   let image = UIImage(data: data) {
                    photos[driver] = image
                }
            }
        }
    }
}
