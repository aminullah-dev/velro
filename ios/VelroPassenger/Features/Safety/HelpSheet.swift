import SwiftUI
import VelroCore

/// What the ride is, for reading out loud. Everything here is already on the
/// phone, so the sheet works with no connection at all.
struct RideFacts: Equatable {
    let bookingNumber: String
    let driverName: String?
    /// Beside the name, not instead of it: a number is the one thing a
    /// relative or a police post can act on.
    let driverPhone: String?
    let plate: String?
    let origin: String?
    let destination: String?
}

/// Get help: three doors, in the order a person in trouble needs them.
///
/// 1. Dial 119 or 100 -- no data, no permission, and the only door that brings
///    anybody.
/// 2. Send the car's details to someone who will come. The message is written
///    for them and the recipient is chosen in Messages, so VELRO never holds a
///    list of whom a woman in Ghorband would call for help.
/// 3. Tell VELRO -- needs data, and says out loud nobody may read it till morning.
///
/// Above all three, the sentence that keeps the rest honest: VELRO is not an
/// emergency service and cannot send anyone.
struct HelpSheet: View {
    let app: AppModel
    let ride: RideFacts?
    var tripId: String?
    var bookingId: String?
    /// False before sign-in: a report needs a token, and a form that fails on
    /// submit for somebody who has just described being in danger is worse
    /// than not offering it.
    var canReport = true
    var openReports: (() -> Void)?

    @Environment(\.strings) private var strings
    @Environment(\.openURL) private var openURL
    @Environment(\.dismiss) private var dismiss
    @State private var reporting = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: Spacing.md) {
                    if reporting {
                        ReportForm(app: app, tripId: tripId, bookingId: bookingId) { reporting = false }
                    } else {
                        doors
                    }
                }
                .padding(.horizontal, Spacing.gutter)
                .padding(.bottom, Spacing.xl)
            }
            .background(Palette.background)
            .navigationTitle(strings["safety.title"])
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(strings["common.action.close"]) { dismiss() }
                }
            }
        }
        .environment(\.layoutDirection, app.locale.isRTL ? .rightToLeft : .leftToRight)
        .environment(\.strings, app.strings)
        .presentationDetents([.large])
    }

    @ViewBuilder
    private var doors: some View {
        // First, before any button, so it is read before anything is pressed.
        Text(strings["safety.not_rescue"])
            .velroFont(.label)
            .foregroundStyle(Palette.onSurfaceVariant)
            .padding(.top, Spacing.sm)

        let contacts = app.safety.contacts
        ForEach(contacts.emergencyNumbers, id: \.self) { number in
            // The dialler opens with the number and she presses call herself:
            // the app never places a call nobody saw.
            PrimaryButton(label: strings["safety.call_emergency", ["number": number]]) {
                if let url = URL(string: "tel:\(number)") { openURL(url) }
            }
            .accessibilityIdentifier("help.call")
        }
        if !contacts.emergencyNumbers.isEmpty {
            Text(strings["safety.call_emergency_hint"])
                .velroFont(.caption)
                .foregroundStyle(Palette.onSurfaceVariant)
        }

        if let ride {
            SecondaryButton(label: strings["safety.tell_someone"]) { tellSomeone(ride) }
                .padding(.top, Spacing.sm)
            Text(strings["safety.tell_someone_hint"])
                .velroFont(.caption)
                .foregroundStyle(Palette.onSurfaceVariant)
            RideDetails(ride: ride)
                .padding(.top, Spacing.sm)
        } else {
            Text(strings["safety.no_ride"])
                .velroFont(.label)
                .foregroundStyle(Palette.onSurfaceVariant)
        }

        if canReport {
            SecondaryButton(label: strings["safety.report"]) { reporting = true }
                .padding(.top, Spacing.sm)
                .accessibilityIdentifier("help.report")
            Text(strings["safety.report_hint", ["number": contacts.emergencyNumbers.first ?? ""]])
                .velroFont(.caption)
                .foregroundStyle(Palette.onSurfaceVariant)
            if let openReports {
                // Asked for first, opened by the screen underneath once this
                // sheet has gone: a push made while a sheet is still closing
                // is dropped.
                SecondaryButton(label: strings["safety.my_reports"]) {
                    openReports()
                    dismiss()
                }
                .accessibilityIdentifier("help.reports")
            }
        }
    }

    /// The message, written for them: a frightened person should not be
    /// composing a sentence. Messages opens; she picks who.
    private func tellSomeone(_ ride: RideFacts) {
        let unknown = strings["common.value.unknown"]
        let body = strings["safety.sms_body", [
            "plate": ride.plate ?? unknown,
            "driver": ride.driverName ?? strings["common.value.no_name"],
            "driver_phone": ride.driverPhone ?? unknown,
            "booking": ride.bookingNumber,
            "origin": ride.origin ?? unknown,
            "destination": ride.destination ?? unknown,
        ]]
        var components = URLComponents()
        components.scheme = "sms"
        components.path = ""
        components.queryItems = [URLQueryItem(name: "body", value: body)]
        if let query = components.percentEncodedQuery, let url = URL(string: "sms:&\(query)") {
            openURL(url)
        }
    }
}

/// The card read down a phone line: on a call to 119 or to a relative these
/// are the facts asked for, and reading them beats remembering them.
private struct RideDetails: View {
    let ride: RideFacts
    @Environment(\.strings) private var strings

    var body: some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.xs) {
                Text(strings["safety.details_title"])
                    .velroFont(.label, weight: .medium)
                if let plate = ride.plate {
                    Text(plate)
                        .font(.system(.title2, design: .monospaced).weight(.bold))
                        .environment(\.layoutDirection, .leftToRight)
                }
                Text(ride.driverName ?? strings["common.value.no_name"])
                    .velroFont(.body)
                if let phone = ride.driverPhone {
                    Text(phone).font(.body.monospacedDigit()).environment(\.layoutDirection, .leftToRight)
                }
                Text(ride.bookingNumber).font(.body).environment(\.layoutDirection, .leftToRight)
                if let origin = ride.origin, let destination = ride.destination {
                    Text(strings["ride.journey.from_to", ["origin": origin, "destination": destination]])
                        .velroFont(.label)
                }
                Text(strings["safety.read_aloud"])
                    .velroFont(.caption)
                    .foregroundStyle(Palette.onSurfaceVariant)
            }
            .foregroundStyle(Palette.onSurface)
        }
    }
}

/// Tell VELRO what happened: the last door and the least prominent, because
/// it needs a connection and reaches a small team that is not always awake.
private struct ReportForm: View {
    let app: AppModel
    let tripId: String?
    let bookingId: String?
    let close: () -> Void

    @Environment(\.strings) private var strings
    @State private var category: String?
    @State private var text = ""
    @State private var sending = false
    @State private var error: APIError?
    @State private var reference: String?

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.md) {
            Text(strings["safety.report"])
                .velroFont(.heading, weight: .medium)
                .padding(.top, Spacing.sm)
            // Before the form: somebody in danger right now should be dialling.
            Text(strings["safety.report_hint", ["number": app.safety.contacts.emergencyNumbers.first ?? ""]])
                .velroFont(.caption)
                .foregroundStyle(Palette.onSurfaceVariant)

            if let reference {
                // The one thing she keeps, read down a phone line: Latin.
                Text(reference)
                    .font(.system(.title2, design: .monospaced).weight(.bold))
                    .environment(\.layoutDirection, .leftToRight)
                    .accessibilityIdentifier("report.reference")
                Text(strings["safety.report_sent", ["reference": reference]])
                    .velroFont(.label)
                SecondaryButton(label: strings["common.action.close"], action: close)
                    .accessibilityIdentifier("report.close")
            } else {
                if let error { InlineError(error: error) }
                ForEach(app.safety.contacts.categories, id: \.self) { code in
                    Button { category = code } label: {
                        HStack(spacing: Spacing.md) {
                            Image(systemName: category == code ? "largecircle.fill.circle" : "circle")
                                .foregroundStyle(category == code ? Palette.primary : Palette.outline)
                            Text(TicketCategory.label(code, strings))
                                .velroFont(.body)
                                .foregroundStyle(Palette.onSurface)
                            Spacer()
                        }
                        .frame(minHeight: 44)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityAddTraits(category == code ? .isSelected : [])
                    .accessibilityIdentifier("report.category.\(code)")
                }
                // Her own words, not an operator's prompt.
                VStack(alignment: .leading, spacing: Spacing.xs) {
                    Text(strings["safety.report_placeholder"])
                        .velroFont(.label)
                        .foregroundStyle(Palette.onSurfaceVariant)
                    TextEditor(text: $text)
                        .frame(minHeight: 110)
                        .padding(Spacing.sm)
                        .scrollContentBackground(.hidden)
                        .background(Palette.surface, in: RoundedRectangle(cornerRadius: Radius.md))
                        .overlay(RoundedRectangle(cornerRadius: Radius.md).strokeBorder(Palette.outline))
                        .accessibilityLabel(strings["safety.report_placeholder"])
                        .accessibilityIdentifier("report.text")
                }
                PrimaryButton(label: strings["safety.report"], enabled: canSubmit, loading: sending) {
                    Task { await submit() }
                }
                .accessibilityIdentifier("report.submit")
                SecondaryButton(label: strings["common.action.back"], action: close)
            }
        }
        .foregroundStyle(Palette.onSurface)
    }

    private var canSubmit: Bool {
        category != nil && text.trimmingCharacters(in: .whitespacesAndNewlines).count >= 3 && !sending
    }

    private func submit() async {
        guard let category, canSubmit else { return }
        sending = true
        error = nil
        let body = text.trimmingCharacters(in: .whitespacesAndNewlines)
        switch await app.client.send(API.raiseTicket(category: category, body: body, tripId: tripId, bookingId: bookingId)) {
        case .success(let raised): reference = raised.reference
        case .failure(let failure): if failure != .cancelled { error = failure }
        }
        sending = false
    }
}

/// Report categories by name. Written out rather than built from the code, so
/// the locale coverage test sees every key.
enum TicketCategory {
    static func label(_ code: String, _ strings: Strings) -> String {
        switch code {
        case "SAFETY": strings["ticket.category.safety"]
        case "DRIVER_CONDUCT": strings["ticket.category.driver_conduct"]
        case "PASSENGER_CONDUCT": strings["ticket.category.passenger_conduct"]
        case "APP_PROBLEM": strings["ticket.category.app_problem"]
        case "FARE_DISPUTE": strings["ticket.category.fare_dispute"]
        case "LOST_ITEM": strings["ticket.category.lost_item"]
        case "VEHICLE_CONDITION": strings["ticket.category.vehicle_condition"]
        default: strings["ticket.category.other"]
        }
    }
}
