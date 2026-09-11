import SwiftUI
import VelroCore

/// The driver's working screen. One action at a time: whatever matters right
/// now -- the trip, a dispatched offer, the passengers waiting, or the switch
/// that lets him see them -- read at arm's length in a parked car.
struct DriverHomeView: View {
    @Environment(\.strings) private var strings
    @State private var model: DriverHomeModel
    @State private var helpOpen = false
    @State private var reportsAfterHelp = false
    private let app: AppModel

    init(app: AppModel) {
        self.app = app
        _model = State(initialValue: DriverHomeModel(app: app))
    }

    var body: some View {
        Group {
            if model.assignment?.isRiding == true {
                DriverRideView(model: model) { helpOpen = true }
            } else {
                working
            }
        }
        .onAppear { Task { await model.refresh() } }
        .task { await model.poll() }
        // Help above everything else on this screen, loading and failure
        // included: a driver alone on a mountain road at night with no data
        // still needs an emergency number.
        .sheet(isPresented: $helpOpen, onDismiss: openReportsIfAsked) {
            HelpSheet(app: app, ride: rideFacts, tripId: model.assignment?.trip.id, openReports: { reportsAfterHelp = true })
        }
        .overlay(alignment: .bottom) { NoticeToast(text: $model.notice) }
    }

    private var rideFacts: RideFacts? {
        guard let assignment = model.assignment else { return nil }
        return RideFacts(
            bookingNumber: assignment.trip.number,
            driverName: model.profile?.fullName,
            // His own sheet: the number he would read out is his own.
            driverPhone: nil,
            plate: model.profile?.vehicle?.plateNumber,
            origin: assignment.trip.originStationName,
            destination: assignment.trip.destinationName
        )
    }

    private func openReportsIfAsked() {
        guard reportsAfterHelp else { return }
        reportsAfterHelp = false
        app.router.open(.reports)
    }

    // MARK: The working screen

    private var working: some View {
        GeometryReader { geometry in
            ScrollView {
                VStack(spacing: 0) {
                    header(topInset: geometry.safeAreaInsets.top)
                    VStack(alignment: .leading, spacing: Spacing.md) {
                        content
                    }
                    .padding(.horizontal, Spacing.gutter)
                    .padding(.top, Spacing.lg)
                    .padding(.bottom, Spacing.xxl)
                }
            }
            .ignoresSafeArea(edges: .top)
            .refreshable { await model.refresh() }
        }
        .background(Palette.background)
        .toolbar(.hidden, for: .navigationBar)
    }

    private func header(topInset: CGFloat) -> some View {
        BrandHeader(title: strings["app.name"], topInset: topInset) {
            Button { helpOpen = true } label: {
                Text(strings["safety.title"])
                    .velroFont(.label, weight: .medium)
                    .frame(minHeight: Sizing.touchTarget)
                    .contentShape(Rectangle())
            }
            .accessibilityIdentifier("home.help")
            Button { app.router.open(.profile) } label: {
                Image(systemName: "person.crop.circle.fill")
                    .font(.system(size: 26))
                    .frame(minWidth: Sizing.touchTarget, minHeight: Sizing.touchTarget)
                    .contentShape(Rectangle())
            }
            .accessibilityLabel(strings["driver.profile.title"])
            .accessibilityIdentifier("home.profile")
        } content: {
            if !model.notADriver {
                Text(model.profile?.fullName.map { strings["driver.greeting", ["name": $0]] } ?? strings["driver.greeting_no_name"])
                    .velroFont(.heading)
                    .foregroundStyle(Palette.brandSubtitle)
                    .padding(.top, Spacing.sm)
            }
        }
    }

    @ViewBuilder
    private var content: some View {
        if model.isLoading {
            LoadingState()
        } else if model.notADriver {
            BecomeADriver { app.router.open(.documents) }
        } else if let profile = model.profile {
            if model.isStale {
                // Saved data, honestly labelled: a board that failed to
                // refresh looks exactly like a board with no work on it.
                Text(strings["common.state.offline"])
                    .velroFont(.caption)
                    .foregroundStyle(Palette.onSurfaceVariant)
            }
            DriverSummary(profile: profile)
            // His papers and his car, open to him whether or not he is
            // approved: an approved driver must still see a licence about to
            // expire, and correct the car a passenger is told to look for.
            HStack(spacing: Spacing.sm) {
                SecondaryButton(label: strings["driver.documents.title"]) { app.router.open(.documents) }
                SecondaryButton(label: strings["driver.vehicle.title"]) { app.router.open(.vehicle) }
            }

            if !profile.canWork {
                PendingApproval(profile: profile, openDocuments: { app.router.open(.documents) }, openVehicle: { app.router.open(.vehicle) })
            } else {
                OnlineToggle(isOnline: model.isOnline, busy: model.isBusy) { Task { await model.toggleOnline() } }
            }

            if let error = model.error { InlineError(error: error) }

            InboxCard(inbox: model.inbox) { Task { await model.markInboxRead() } }

            work
                .padding(.top, Spacing.sm)

            EarningsCard(earnings: model.earnings) { app.router.open(.earnings) }
                .padding(.top, Spacing.md)
        } else if let error = model.error {
            ErrorState(error: error) { Task { await model.refresh() } }
        }
    }

    @ViewBuilder
    private var work: some View {
        if let assignment = model.assignment {
            TripCard(model: model, assignment: assignment)
        } else if !model.dispatchOffers.isEmpty {
            Text(strings["driver.section.requests"])
                .velroFont(.heading, weight: .medium)
                .foregroundStyle(Palette.onSurface)
            ForEach(model.dispatchOffers) { offer in
                DispatchOfferCard(offer: offer, busy: model.isBusy) {
                    Task { await model.acceptDispatch(offer.trip.id) }
                }
            }
        } else if model.isOnline {
            Text(strings["driver.section.requests"])
                .velroFont(.heading, weight: .medium)
                .foregroundStyle(Palette.onSurface)
            // The work itself, not a door to it: nothing rings on this phone,
            // so if the screen does not say it, he does not know it.
            if model.waiting.isEmpty {
                Text(strings["driver.requests.none"])
                    .velroFont(.body)
                    .foregroundStyle(Palette.onSurfaceVariant)
                SecondaryButton(label: strings["driver.board.title"]) { app.router.open(.board) }
            } else {
                ForEach(model.waiting.prefix(3)) { request in
                    Button { app.router.open(.board) } label: { WaitingRequestCard(request: request) }
                        .buttonStyle(PressStyle())
                }
                PrimaryButton(label: strings["driver.board.title"]) { app.router.open(.board) }
                    .accessibilityIdentifier("home.board")
            }
        } else {
            OfflineNotice(waiting: model.waiting.count)
        }
    }
}

// MARK: - Pieces

private struct BecomeADriver: View {
    let apply: () -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        VStack(alignment: .leading, spacing: Spacing.md) {
            Text(strings["driver.welcome.title"])
                .velroFont(.title, weight: .bold)
                .foregroundStyle(Palette.onSurface)
            Text(strings["driver.welcome.body"])
                .velroFont(.body)
                .foregroundStyle(Palette.onSurfaceVariant)
            PrimaryButton(label: strings["driver.documents.apply"], action: apply)
                .accessibilityIdentifier("home.apply")
        }
    }
}

private struct DriverSummary: View {
    let profile: DriverProfile
    @Environment(\.strings) private var strings

    var body: some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.xs) {
                if let vehicle = profile.vehicle {
                    HStack(spacing: Spacing.sm) {
                        if let name = vehicle.makeAndModel {
                            Text(name)
                                .velroFont(.heading, weight: .medium)
                                .foregroundStyle(Palette.onSurface)
                        }
                        PlateText(plate: vehicle.plateNumber)
                    }
                } else {
                    Text(strings["driver.vehicle.none"])
                        .velroFont(.label)
                        .foregroundStyle(Palette.onSurfaceVariant)
                }
                if let rating = profile.ratingAverage {
                    Label(
                        "\(Numerals.localise(String(format: "%.1f", rating), strings.locale))  (\(Numerals.localise(String(profile.ratingCount ?? 0), strings.locale)))",
                        systemImage: "star.fill"
                    )
                    .velroFont(.label)
                    .foregroundStyle(Palette.accent)
                }
            }
        }
    }
}

private struct PendingApproval: View {
    let profile: DriverProfile
    let openDocuments: () -> Void
    let openVehicle: () -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.sm) {
                Text(strings["driver.pending.title"])
                    .velroFont(.heading, weight: .medium)
                    .foregroundStyle(Palette.onSurface)
                Text(strings["driver.pending.body"])
                    .velroFont(.label)
                    .foregroundStyle(Palette.onSurfaceVariant)
                let missing = profile.missingDocuments ?? []
                if !missing.isEmpty {
                    Text(missing.map { strings["document.type.\($0.lowercased())"] }.joined(separator: " • "))
                        .velroFont(.caption)
                        .foregroundStyle(Palette.accent)
                }
                if profile.blockedByVehicle {
                    Text(strings[vehicleKey])
                        .velroFont(.caption)
                        .foregroundStyle(Palette.accent)
                }
                SecondaryButton(label: strings["driver.documents.title"], action: openDocuments)
                if profile.blockedByVehicle {
                    SecondaryButton(label: strings["driver.vehicle.title"], action: openVehicle)
                }
            }
        }
    }

    private var vehicleKey: String {
        switch profile.vehicle?.status {
        case nil: "driver.vehicle.none"
        case .suspended?: "driver.vehicle.suspended"
        default: "driver.vehicle.awaiting"
        }
    }
}

private struct OnlineToggle: View {
    let isOnline: Bool
    let busy: Bool
    let toggle: () -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        VelroCard {
            Toggle(isOn: Binding(get: { isOnline }, set: { _ in toggle() })) {
                Text(strings[isOnline ? "driver.status.online" : "driver.status.offline"])
                    .velroFont(.heading, weight: .bold)
                    .foregroundStyle(isOnline ? Palette.primary : Palette.onSurfaceVariant)
            }
            .tint(Palette.primary)
            .disabled(busy)
            .accessibilityIdentifier("home.online")
        }
    }
}

private struct OfflineNotice: View {
    let waiting: Int
    @Environment(\.strings) private var strings

    var body: some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.xs) {
                Text(strings["driver.offline.title"])
                    .velroFont(.heading, weight: .medium)
                    .foregroundStyle(Palette.onSurface)
                Text(strings["driver.offline.body"])
                    .velroFont(.label)
                    .foregroundStyle(Palette.onSurfaceVariant)
                if waiting > 0 {
                    Text(strings["driver.offline.waiting"])
                        .velroFont(.label, weight: .bold)
                        .foregroundStyle(Palette.primary)
                        .padding(.top, Spacing.xs)
                }
            }
        }
    }
}

/// One waiting passenger. The fare is the loudest thing on it: what a driver
/// decides with is the money and the road, in that order.
struct WaitingRequestCard: View {
    let request: RideRequest
    @Environment(\.strings) private var strings

    var body: some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.xxs) {
                Text(MoneyFormatter.format(request.askingTotal, strings: strings))
                    .velroFont(.title, weight: .bold)
                    .foregroundStyle(Palette.primary)
                Text(strings["ride.journey.from_to", [
                    "origin": request.originStationName ?? strings["common.value.unknown"],
                    "destination": request.destinationName ?? strings["common.value.unknown"],
                ]])
                .velroFont(.body)
                .foregroundStyle(Palette.onSurface)
                if let departure = request.departure {
                    Text(Calendars.dateTime(departure, strings.locale))
                        .velroFont(.caption)
                        .foregroundStyle(Palette.accent)
                }
                if request.alreadyOffered == true {
                    Text(strings["driver.board.already_offered"])
                        .velroFont(.caption)
                        .foregroundStyle(Palette.onSurfaceVariant)
                }
            }
        }
    }
}

private struct DispatchOfferCard: View {
    let offer: DispatchOffer
    let busy: Bool
    let accept: () -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.sm) {
                if let departure = offer.trip.departure {
                    Text(Calendars.time(departure, strings.locale))
                        .velroFont(.title, weight: .bold)
                        .foregroundStyle(Palette.onSurface)
                }
                JourneyLine(origin: offer.trip.originStationName, destination: offer.trip.destinationName)
                Text(strings["driver.label.passengers"] + ": " +
                     Numerals.localise(String(offer.trip.seatCapacity - offer.trip.seatsAvailable), strings.locale))
                    .velroFont(.label)
                    .foregroundStyle(Palette.onSurfaceVariant)
                PrimaryButton(label: strings["driver.action.accept"], enabled: !busy, loading: busy, action: accept)
            }
        }
    }
}

private struct InboxCard: View {
    let inbox: Inbox?
    let markRead: () -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        let unread = (inbox?.notifications ?? []).filter(\.isUnread)
        if !unread.isEmpty {
            VelroCard {
                VStack(alignment: .leading, spacing: Spacing.sm) {
                    ForEach(unread.prefix(3)) { note in
                        Text(strings[note.messageKey, note.arguments])
                            .velroFont(.body)
                            .foregroundStyle(Palette.onSurface)
                    }
                    SecondaryButton(label: strings["inbox.mark_read"], action: markRead)
                }
            }
        }
    }
}

private struct EarningsCard: View {
    let earnings: Earnings?
    let open: () -> Void
    @Environment(\.strings) private var strings

    var body: some View {
        VelroCard {
            VStack(alignment: .leading, spacing: Spacing.sm) {
                Text(strings["earnings.title"])
                    .velroFont(.heading, weight: .medium)
                    .foregroundStyle(Palette.onSurface)
                if let earnings {
                    Text(strings[earnings.owes ? "driver.earnings.owed" : "earnings.label.available"])
                        .velroFont(.label)
                        .foregroundStyle(Palette.onSurfaceVariant)
                    Text(MoneyFormatter.format(earnings.owes ? earnings.owed : earnings.available, strings: strings))
                        .velroFont(.display, weight: .bold)
                        .foregroundStyle(earnings.owes ? Palette.error : Palette.primary)
                    if earnings.owes {
                        Text(strings["driver.earnings.owed_explained"])
                            .velroFont(.caption)
                            .foregroundStyle(Palette.onSurfaceVariant)
                    }
                    row(strings["earnings.label.lifetime"], MoneyFormatter.format(earnings.lifetimeEarned, strings: strings))
                    row(strings["earnings.label.trips"], Numerals.localise(String(earnings.completedTrips), strings.locale))
                } else {
                    Text(strings["common.state.loading"])
                        .velroFont(.label)
                        .foregroundStyle(Palette.onSurfaceVariant)
                }
                SecondaryButton(label: strings["driver.earnings.title"], action: open)
                    .accessibilityIdentifier("home.earnings")
            }
        }
    }

    private func row(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).velroFont(.label).foregroundStyle(Palette.onSurfaceVariant)
            Spacer()
            Text(value).velroFont(.label, weight: .medium).foregroundStyle(Palette.onSurface)
        }
    }
}

/// A sentence that says what just happened, for a few seconds.
struct NoticeToast: View {
    @Binding var text: String?

    var body: some View {
        Group {
            if let text {
                Text(text)
                    .velroFont(.label, weight: .medium)
                    .foregroundStyle(Palette.onPrimary)
                    .padding(.horizontal, Spacing.lg)
                    .padding(.vertical, Spacing.md)
                    .background(Palette.onSurface.opacity(0.92), in: Capsule())
                    .padding(.bottom, Spacing.xl)
                    .padding(.horizontal, Spacing.gutter)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .task(id: text) {
                        try? await Task.sleep(for: .seconds(4))
                        self.text = nil
                    }
                    .accessibilityAddTraits(.updatesFrequently)
            }
        }
        .animation(.easeOut(duration: 0.2), value: text)
    }
}
