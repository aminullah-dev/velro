import SwiftUI
import VelroCore

/// A status as a word in a pill (the panel's StatusChip). The word is always
/// there; colour never carries the meaning alone. A status with no
/// translation shows its raw value -- a visible bug, not a blank.
///
///     StatusChip(trip: trip.status)
///     StatusChip(document: document.status)
///     StatusChip(strings["admin.dispatch.at_risk"], tone: .attention)
struct StatusChip: View {
    @Environment(\.strings) private var strings
    private let key: String?
    private let text: String
    private let tone: StatusTone

    /// Text already in the reader's language.
    init(_ text: String, tone: StatusTone = .neutral) {
        self.key = nil
        self.text = text
        self.tone = tone
    }

    /// A message key, with the raw value to show if the key is missing.
    init(key: String, raw: String, tone: StatusTone) {
        self.key = key
        self.text = raw
        self.tone = tone
    }

    init(trip status: TripStatus) { self.init(key: status.messageKey, raw: status.rawValue, tone: status.tone) }
    init(booking status: BookingStatus) { self.init(key: status.messageKey, raw: status.rawValue, tone: status.tone) }
    init(driver status: DriverApprovalStatus) { self.init(key: status.messageKey, raw: status.rawValue, tone: status.tone) }
    init(vehicle status: VehicleStatus) { self.init(key: status.messageKey, raw: status.rawValue, tone: status.tone) }
    init(document status: DocumentStatus) { self.init(key: status.messageKey, raw: status.rawValue, tone: status.tone) }
    init(settlement status: SettlementStatus) { self.init(key: status.messageKey, raw: status.rawValue, tone: status.tone) }
    init(ticket status: TicketStatus) { self.init(key: status.messageKey, raw: status.rawValue, tone: status.tone) }

    init(availability: DriverAvailability) {
        switch availability {
        case .online: self.init(key: "driver.status.online", raw: availability.rawValue, tone: .active)
        case .onTrip: self.init(key: "admin.map.on_trip", raw: availability.rawValue, tone: .attention)
        case .offline: self.init(key: "driver.status.offline", raw: availability.rawValue, tone: .ended)
        case .busy: self.init(key: "driver.status.online", raw: availability.rawValue, tone: .neutral)
        }
    }

    /// A role's name: "role.dispatcher".
    init(role: String) { self.init(key: "role." + role.lowercased(), raw: role, tone: .neutral) }

    private var label: String {
        if let key, strings.has(key) { strings[key] } else { text }
    }

    var body: some View {
        let colors = Palette.chip(tone)
        Text(label)
            .opsFont(.caption, weight: .medium)
            .lineLimit(1)
            .fixedSize()
            .padding(.horizontal, Spacing.s3)
            .padding(.vertical, 3)
            .foregroundStyle(colors.foreground)
            .background(colors.background, in: Capsule())
    }
}
