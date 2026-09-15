import Observation
import SwiftUI
import VelroCore

/// Bookings, newest first (the panel's Bookings.tsx), by status, scrolling on
/// into older pages. The boarding code is deliberately absent: the server does
/// not send it to staff.
///
/// Another screen may open it on a status: `navigator.open(.bookings,
/// filter: "status:NO_SHOW")`.
struct BookingsView: View {
    @Environment(OpsModel.self) private var ops
    @Environment(\.strings) private var strings
    @State private var model = OpBookingsModel()
    @State private var selectedID: String?

    init() {}

    var body: some View {
        OpSplitReader { isSplit in
            if isSplit {
                OpSplitLayout(listWidth: 420) {
                    list(isSplit: true)
                } detail: {
                    if let booking = model.pager.items.first(where: { $0.id == selectedID }) {
                        OpBookingDetailView(booking: booking).id(booking.id)
                    } else {
                        OpNothingSelected(messageKey: "ops.bookings.choose", systemImage: "person.2")
                    }
                }
            } else {
                list(isSplit: false)
                    .navigationDestination(for: AdminBooking.self) { booking in
                        OpBookingDetailView(booking: booking)
                    }
            }
        }
        .background(Palette.background)
        .navigationTitle(strings["admin.nav.bookings"])
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                OpRefreshButton { [model] in await model.pager.refresh() }
            }
        }
        .task { [model, ops] in
            model.apply(deepLink: ops.navigator.takeFilter(for: .bookings))
            await model.reload(ops)
        }
        .poll(every: .seconds(60)) { [model] in await model.pager.refresh() }
    }

    private var statusBinding: Binding<BookingStatus?> {
        Binding(get: { model.status }, set: { value in
            guard value != model.status else { return }
            model.status = value
            selectedID = nil
            Task { [model, ops] in await model.reload(ops) }
        })
    }

    @ViewBuilder
    private func list(isSplit: Bool) -> some View {
        VStack(spacing: 0) {
            OpChipBar(options: [.init(value: BookingStatus?.none, label: strings["admin.filter.all"])]
                      + BookingStatus.allCases.map {
                          .init(value: BookingStatus?.some($0), label: OpText.word($0.messageKey, raw: $0.rawValue, strings))
                      },
                      selection: statusBinding)
            Divider()
            let pager = model.pager
            if pager.isFirstLoad {
                LoadingView()
            } else if let error = pager.error {
                ErrorView(error: error) { [model, ops] in await model.reload(ops) }
            } else if pager.items.isEmpty {
                EmptyStateView(messageKey: "admin.empty.bookings", systemImage: "person.2")
            } else {
                List(selection: isSplit ? $selectedID : .constant(nil)) {
                    ForEach(pager.items) { booking in
                        if isSplit {
                            OpBookingRowView(booking: booking).tag(booking.id)
                        } else {
                            NavigationLink(value: booking) { OpBookingRowView(booking: booking) }
                        }
                    }
                    OpPagerFooter(pager: pager)
                }
                .listStyle(.plain)
                // Selected beside its detail: a light ground the row's own ink reads on.
                .tint(isSplit ? Palette.bannerInfo : Palette.accent)
                .scrollContentBackground(.hidden)
                .refreshable { await pager.refresh() }
            }
        }
    }
}

// MARK: - The model

@MainActor
@Observable
final class OpBookingsModel {
    var status: BookingStatus?
    let pager = OpPager<AdminBooking>(pageSize: 50)

    func apply(deepLink: String?) {
        guard let deepLink else { return }
        let raw = deepLink.hasPrefix("status:") ? String(deepLink.dropFirst("status:".count)) : deepLink
        if let value = BookingStatus(rawValue: raw.uppercased()) { status = value }
    }

    func reload(_ ops: OpsModel) async {
        let status = status
        await pager.reload { [ops] limit, offset in
            await ops.sendWithMeta(AdminAPI.bookings(status: status, limit: limit, offset: offset))
        }
    }
}

// MARK: - A row

private struct OpBookingRowView: View {
    @Environment(\.strings) private var strings
    let booking: AdminBooking

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.s1) {
            HStack(spacing: Spacing.s2) {
                LTRText(booking.number)
                    .opsFont(.label, weight: .medium)
                    .foregroundStyle(Palette.text)
                StatusChip(booking: booking.status)
                Spacer(minLength: 0)
                MoneyText(booking.fare)
                    .opsFont(.label, weight: .medium)
                    .foregroundStyle(Palette.text)
            }
            HStack(spacing: Spacing.s2) {
                Text(OpText.name(booking.passengerName, strings))
                    .lineLimit(1)
                if let phone = booking.passengerPhone {
                    LTRText(phone).foregroundStyle(Palette.textMuted)
                }
            }
            .opsFont(.body)
            .foregroundStyle(Palette.text)
            HStack(spacing: Spacing.s2) {
                Image(systemName: "car.2").accessibilityHidden(true)
                LTRText(booking.tripNumber)
                DotSeparator().accessibilityHidden(true)
                Label(OpsFormat.count(booking.seatCount, strings), systemImage: "person.fill")
                    .accessibilityLabel(strings["admin.col.seats"] + " " + OpsFormat.count(booking.seatCount, strings))
                DotSeparator().accessibilityHidden(true)
                Text(OpBookingText.payment(booking, strings)).lineLimit(1)
                Spacer(minLength: 0)
                DateText(booking.createdAt, style: .relative)
            }
            .opsFont(.caption)
            .foregroundStyle(Palette.textMuted)
        }
        .padding(.vertical, Spacing.s1)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("bookings.row." + booking.number)
    }
}

// MARK: - The detail

struct OpBookingDetailView: View {
    @Environment(\.strings) private var strings
    let booking: AdminBooking

    var body: some View {
        Form {
            Section {
                OpDetailTitle(booking.number, subtitle: OpText.name(booking.passengerName, strings), isLatin: true) {
                    StatusChip(booking: booking.status)
                }
                .padding(.vertical, Spacing.s2)
            }
            Section {
                OpField("admin.col.passenger", text: OpText.name(booking.passengerName, strings))
                OpField("admin.col.phone") { PhoneLink(booking.passengerPhone) }
                OpField("admin.nav.trips") { LTRText(booking.tripNumber) }
                OpField("admin.col.seats", text: OpsFormat.count(booking.seatCount, strings))
            }
            Section {
                OpField("admin.col.fare") { MoneyText(booking.fare) }
                OpField("admin.col.payment", text: OpText.word(
                    "payment.method." + booking.paymentMethod.lowercased(), raw: booking.paymentMethod, strings))
                if let status = booking.paymentStatus {
                    OpField("admin.col.status", text: OpText.word("payment.status." + status.lowercased(), raw: status, strings))
                }
            } header: {
                OpFormHeader(titleKey: "admin.col.payment")
            }
            Section {
                OpField("admin.col.created") {
                    VStack(alignment: .trailing, spacing: 2) {
                        DateText(booking.createdAt)
                        DateText(booking.createdAt, style: .relative)
                            .opsFont(.caption)
                            .foregroundStyle(Palette.textMuted)
                    }
                }
            }
        }
        .formStyle(.grouped)
        .scrollContentBackground(.hidden)
        .background(Palette.background)
        .opNavigationTitle(booking.number)
    }
}
