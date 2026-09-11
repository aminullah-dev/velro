import Observation
import SwiftUI
import UIKit
import VelroCore

/// The ride, watched: the map first and largest, then only what a person at a
/// roadside needs -- how long, whose car, which plate, and a button that
/// dials, because here a phone call is the chat system.
@MainActor
@Observable
final class TrackRideModel {
    private(set) var booking: Booking?
    private(set) var map: TripMap?
    private(set) var driver: RideDriver?
    private(set) var photo: UIImage?
    private(set) var vehicle: VehicleLocation?
    /// From the road's own length and its routing average, or nil. Never a guess.
    private(set) var etaMinutes: Int?
    /// Her own name, for the foot of the ride map.
    private(set) var passengerName: String?
    /// The next warning on the road ahead of the car, once she is on board.
    private(set) var roadAhead: RoadAhead.Next?
    /// She was on board and no longer is: the ride is over, and the screen
    /// goes back to the booking, where the rating is.
    private(set) var rideEnded = false

    private let bookingId: String
    private let app: AppModel

    init(app: AppModel, bookingId: String) {
        self.app = app
        self.bookingId = bookingId
        booking = app.personal.value(Booking.self, key: "booking-\(bookingId)")
    }

    /// Faster than the booking page: this screen exists to watch a dot move.
    /// Faster still on board, where the warning at the top follows the car.
    func poll() async {
        if case .success(let me) = await app.client.send(API.profile()) { passengerName = me.fullName }
        await refresh()
        while !Task.isCancelled {
            try? await Task.sleep(for: .seconds(booking?.status == .onboard ? 8 : 15))
            if Task.isCancelled { return }
            await refresh()
        }
    }

    private func refresh() async {
        if let fresh = await app.client.send(API.booking(bookingId), caching: "booking-\(bookingId)", in: app.personal).value {
            if booking?.status == .onboard && fresh.status != .onboard { rideEnded = true }
            booking = fresh
        }
        guard let booking else { return }
        if map == nil, case .success(let drawn) = await app.client.send(
            API.journeyMap(originStationId: booking.pickupStationId, destinationId: booking.dropoffDestinationId)
        ) { map = drawn }
        // The driver can be assigned mid-wait.
        if driver == nil, case .success(let found) = await app.client.sendNullable(API.bookingDriver(bookingId)), let found {
            driver = found
            if case .success(let data) = await app.client.data(API.driverPhoto(found.driverId)) {
                photo = UIImage(data: data)
            }
        }
        if case .success(let ping) = await app.client.sendNullable(API.vehicleLocation(bookingId)) {
            vehicle = ping
        } else {
            vehicle = nil
        }
        etaMinutes = eta(booking)
        if let map, let vehicle {
            roadAhead = RoadAhead.next(road: map.road, car: (vehicle.latitude, vehicle.longitude), alerts: map.alerts ?? [])
        } else {
            roadAhead = nil
        }
    }

    /// Before boarding the car is coming to her station; after, both are
    /// going to the destination. The road is the same line.
    private func eta(_ booking: Booking) -> Int? {
        guard let map, let vehicle else { return nil }
        let target = booking.status == .onboard ? map.destination : map.origin
        guard let target else { return nil }
        return Eta.minutes(
            road: map.road,
            car: (vehicle.latitude, vehicle.longitude),
            target: (target.latitude, target.longitude),
            averageKmh: map.avgSpeedKmh
        )
    }

    /// For the help sheet, from the freshest copy: the live driver card wins,
    /// taken whole -- after a reassignment a relative must not be sent one
    /// man's name beside another car's plate.
    var rideFacts: RideFacts? {
        guard let booking else { return nil }
        return RideFacts(
            bookingNumber: booking.number,
            driverName: driver == nil ? booking.driverName : driver?.name,
            driverPhone: driver?.phone ?? booking.driverPhone,
            plate: driver == nil ? booking.vehiclePlate : driver?.vehicle?.plateNumber,
            origin: map?.origin?.name ?? booking.pickupStationName,
            destination: map?.destination?.name ?? booking.dropoffDestinationName
        )
    }
}

struct TrackRideView: View {
    @Environment(\.strings) private var strings
    @Environment(\.openURL) private var openURL
    @State private var model: TrackRideModel
    @State private var helpOpen = false
    private let app: AppModel

    init(app: AppModel, bookingId: String) {
        self.app = app
        _model = State(initialValue: TrackRideModel(app: app, bookingId: bookingId))
    }

    var body: some View {
        Group {
            if model.booking?.status == .onboard {
                ride
            } else {
                waiting
            }
        }
        .task { await model.poll() }
        .onChange(of: model.rideEnded) { _, ended in
            if ended { app.router.back() }
        }
        .sheet(isPresented: $helpOpen) {
            HelpSheet(app: app, ride: model.rideFacts, tripId: model.booking?.tripId, bookingId: model.booking?.id)
        }
    }

    /// On board: the map and nothing else but the road's next warning at the
    /// top and who is in the car at the bottom. Help stays -- a small door at
    /// the top, because this is the screen she is looking at in the car.
    private var ride: some View {
        ZStack {
            if let map = model.map {
                JourneyMapView(map: map, vehicle: model.vehicle, height: nil, fullBleed: true)
                    .ignoresSafeArea()
            } else {
                Palette.background.ignoresSafeArea()
            }

            VStack(spacing: Spacing.sm) {
                HStack(alignment: .top, spacing: Spacing.sm) {
                    RoadAheadBanner(next: model.roadAhead)
                    Button { helpOpen = true } label: {
                        Image(systemName: "sos")
                            .font(.headline)
                            .frame(width: Sizing.touchTarget, height: Sizing.touchTarget)
                            .foregroundStyle(Palette.onPrimary)
                            .background(Palette.error, in: Circle())
                            .shadow(color: .black.opacity(0.2), radius: 4, y: 2)
                    }
                    .accessibilityLabel(strings["safety.title"])
                    .accessibilityIdentifier("ride.help")
                }
                Spacer()
                RideNames(driver: model.driver?.name ?? model.booking?.driverName, passenger: model.passengerName)
            }
            .padding(.horizontal, Spacing.lg)
            .padding(.vertical, Spacing.sm)
        }
        .toolbar(.hidden, for: .navigationBar)
        .preference(key: BrandStatusBar.self, value: false)
    }

    private var waiting: some View {
        VelroScreen(title: strings["track.title"]) {
            VStack(alignment: .leading, spacing: Spacing.sm) {
                if let map = model.map {
                    JourneyMapView(map: map, vehicle: model.vehicle, height: nil)
                } else {
                    Spacer()
                }

                if model.booking?.isActive == true {
                    SecondaryButton(label: strings["safety.title"]) { helpOpen = true }
                }

                VStack(alignment: .leading, spacing: Spacing.xxs) {
                    Text(etaText)
                        .velroFont(.title, weight: .bold)
                        .foregroundStyle(Palette.onSurface)
                    if let vehicle = model.vehicle { VehicleAge(seconds: vehicle.ageSeconds) }
                }

                if let driver = model.driver {
                    driverCard(driver)
                } else {
                    Text(strings["track.awaiting_driver"])
                        .velroFont(.label)
                        .foregroundStyle(Palette.onSurfaceVariant)
                }
            }
            .padding(.horizontal, Spacing.gutter)
            .padding(.vertical, Spacing.md)
        }
    }

    private var etaText: String {
        guard let minutes = model.etaMinutes else { return strings["track.eta_unknown"] }
        return minutes < 3 ? strings["track.eta_now"] : strings["track.eta", ["minutes": minutes]]
    }

    private func driverCard(_ driver: RideDriver) -> some View {
        VelroCard {
            HStack(spacing: Spacing.md) {
                DriverAvatar(photo: model.photo)
                VStack(alignment: .leading, spacing: Spacing.xxs) {
                    Text(driver.name ?? strings["common.value.no_name"])
                        .velroFont(.heading, weight: .medium)
                        .foregroundStyle(Palette.onSurface)
                    if let rating = driver.ratingAverage {
                        Label(Numerals.localise(String(format: "%.1f", rating), strings.locale), systemImage: "star.fill")
                            .font(.caption)
                            .foregroundStyle(Palette.onSurfaceVariant)
                    }
                    if let vehicle = driver.vehicle {
                        HStack(spacing: Spacing.xs) {
                            Text([vehicle.brand, vehicle.model, vehicle.colour].compactMap { $0 }.joined(separator: " "))
                                .velroFont(.caption)
                                .foregroundStyle(Palette.onSurfaceVariant)
                            PlateText(plate: vehicle.plateNumber)
                        }
                    }
                }
                Spacer(minLength: Spacing.sm)
                // The phone opens with the number; she presses call herself.
                Button {
                    if let url = URL(string: "tel:\(driver.phone)") { openURL(url) }
                } label: {
                    Label(strings["track.call"], systemImage: "phone.fill")
                        .velroFont(.label, weight: .medium)
                        .padding(.horizontal, Spacing.md)
                        .frame(minHeight: 44)
                        .foregroundStyle(Palette.onPrimary)
                        .background(Palette.primary, in: Capsule())
                }
                .buttonStyle(PressStyle())
            }
        }
    }
}
