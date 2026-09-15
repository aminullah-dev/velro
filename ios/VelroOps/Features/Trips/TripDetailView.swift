import SwiftUI
import VelroCore

/// One trip in full: when and where, who drives it, and everybody booked on it
/// with a number to ring.
struct OpTripDetailView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    let trip: AdminTrip

    var body: some View {
        Form {
            Section {
                OpDetailTitle(trip.number, subtitle: OpText.route(trip.originStationName, trip.destinationName, strings),
                              isLatin: true) {
                    StatusChip(trip: trip.status)
                    StatusChip(OpText.rideKind(trip.rideKind, strings))
                    if OpTripsModel.needsAttention(trip) {
                        StatusChip(strings["admin.dispatch.at_risk"], tone: .attention)
                    }
                }
                .padding(.vertical, Spacing.s2)
            }
            Section {
                OpField("admin.col.departure") {
                    VStack(alignment: .trailing, spacing: 2) {
                        DateText(trip.scheduledDepartureAt)
                        if let departure = trip.departure {
                            Text(OpText.untilDeparture(minutes: Calendars.minutesUntil(departure), strings))
                                .opsFont(.caption)
                                .foregroundStyle(Palette.textMuted)
                        }
                    }
                }
                OpField("admin.col.origin", text: trip.originStationName)
                OpField("admin.col.destination", text: trip.destinationName)
                OpField("admin.col.seats", text: OpText.seats(booked: trip.bookedSeats, capacity: trip.seatCapacity, strings))
                OpField("admin.col.available", text: strings["ride.label.seats_available", [
                    "count": trip.seatsAvailable, "capacity": trip.seatCapacity,
                ]])
            }
            Section {
                if trip.hasDriver {
                    OpField("admin.col.driver", text: OpText.name(trip.driverName, strings))
                    OpField("admin.col.phone") { PhoneLink(trip.driverPhone) }
                    OpField("admin.col.plate") {
                        if let plate = trip.plateNumber { LTRText(plate) } else { Text("—") }
                    }
                } else {
                    Label(strings["admin.filter.needs_driver"], systemImage: "exclamationmark.triangle")
                        .opsFont(.body)
                        .foregroundStyle(Palette.attention)
                    if ops.isOperations, [.scheduled, .requested].contains(trip.status) {
                        Button {
                            ops.navigator.open(.dispatch)
                        } label: {
                            Label(strings["admin.nav.operations"], systemImage: Route.dispatch.symbol)
                        }
                    }
                }
            } header: {
                OpFormHeader(titleKey: "trip.label.driver")
            }
            OpTripBookingsSection(tripId: trip.id)
        }
        .formStyle(.grouped)
        .scrollContentBackground(.hidden)
        .background(Palette.background)
        .opNavigationTitle(trip.number)
    }
}

/// Everybody booked on a trip: the booking, the passenger and a number to
/// ring. A section of its own so dispatch shows it too.
struct OpTripBookingsSection: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    let tripId: String
    @State private var state: LoadState<[AdminBooking]> = .loading

    var body: some View {
        Section {
            switch state {
            case .loading:
                HStack { Spacer(); ProgressView(); Spacer() }
            case .failed(let error):
                VStack(alignment: .leading, spacing: Spacing.s2) {
                    Text(OpText.error(error, strings))
                        .opsFont(.body)
                        .foregroundStyle(Palette.danger)
                    Button(strings["common.action.retry"]) { Task { await load() } }
                        .buttonStyle(.bordered)
                }
            case .loaded(let bookings):
                if bookings.isEmpty {
                    Text(strings["admin.empty.bookings"])
                        .opsFont(.body)
                        .foregroundStyle(Palette.textMuted)
                } else {
                    ForEach(bookings) { booking in
                        OpBookingLine(booking: booking)
                    }
                }
            }
        } header: {
            HStack {
                OpFormHeader(titleKey: "admin.nav.bookings")
                if let count = state.value?.count, count > 0 {
                    Text(OpsFormat.count(count, strings))
                        .opsFont(.label)
                        .foregroundStyle(Palette.textMuted)
                }
            }
        }
        .task(id: tripId) { await load() }
    }

    private func load() async {
        let result = await ops.send(AdminAPI.bookings(tripId: tripId, limit: 100))
        if case .failure(let error) = result, error == .cancelled { return }
        state = LoadState(result, keeping: state)
    }
}

/// A booking in a few lines: who, how many seats, the fare and how it is
/// paid, with the passenger's number to ring.
struct OpBookingLine: View {
    @Environment(\.strings) private var strings
    let booking: AdminBooking

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            HStack(spacing: Spacing.s2) {
                LTRText(booking.number)
                    .opsFont(.label, weight: .medium)
                StatusChip(booking: booking.status)
                Spacer(minLength: 0)
                MoneyText(booking.fare)
                    .opsFont(.label, weight: .medium)
            }
            HStack(spacing: Spacing.s2) {
                Text(OpText.name(booking.passengerName, strings))
                    .opsFont(.body)
                PhoneLink(booking.passengerPhone)
                    .opsFont(.body)
                Spacer(minLength: 0)
            }
            HStack(spacing: Spacing.s2) {
                Label(OpsFormat.count(booking.seatCount, strings), systemImage: "person.fill")
                    .accessibilityLabel(strings["admin.col.seats"] + " " + OpsFormat.count(booking.seatCount, strings))
                DotSeparator().accessibilityHidden(true)
                Text(OpBookingText.payment(booking, strings))
            }
            .opsFont(.caption)
            .foregroundStyle(Palette.textMuted)
        }
        .padding(.vertical, 2)
        .accessibilityElement(children: .contain)
    }
}

enum OpBookingText {
    /// How it is paid, or how far the payment got (Bookings.tsx).
    static func payment(_ booking: AdminBooking, _ strings: Strings) -> String {
        let method = OpText.word("payment.method." + booking.paymentMethod.lowercased(), raw: booking.paymentMethod, strings)
        guard let status = booking.paymentStatus else { return method }
        return method + OpsJoin.separator(strings) + OpText.word("payment.status." + status.lowercased(), raw: status, strings)
    }
}
