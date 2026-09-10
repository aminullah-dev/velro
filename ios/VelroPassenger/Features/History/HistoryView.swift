import Observation
import SwiftUI
import VelroCore

/// Her journeys, section 73: those still to come, which she may need to board
/// or cancel, and those taken, which she only wants a record of. Which status
/// falls on which side is the server's answer, so the two apps agree.
@MainActor
@Observable
final class HistoryModel {
    enum Scope: String, CaseIterable { case upcoming, past }

    private(set) var scope: Scope = .upcoming
    private(set) var bookings: [Booking] = []
    private(set) var isLoading = true
    private(set) var isLoadingMore = false
    private(set) var hasMore = false
    private(set) var isStale = false
    private(set) var error: APIError?
    private var nextOffset = 0
    private let app: AppModel
    private static let page = 15

    init(app: AppModel) { self.app = app }

    private func key(_ scope: Scope) -> String { "history-\(scope.rawValue)" }

    /// A new tab clears the list: finished journeys left under "coming up"
    /// while the new ones load are worse than a spinner. Saved pages first,
    /// because in Ghorband the saved answer is often the only one that comes.
    func show(_ scope: Scope) async {
        self.scope = scope
        bookings = app.personal.value(BookingPage.self, key: key(scope))?.bookings ?? []
        isLoading = bookings.isEmpty
        await refresh()
    }

    /// Re-read the current tab without emptying it: the receipt she was
    /// reading must not vanish under a spinner she asked for.
    func refresh() async {
        let asked = scope
        let result = await app.client.send(API.bookings(scope: asked.rawValue, limit: Self.page), caching: key(asked), in: app.personal)
        guard asked == scope else { return }
        if let page = result.value {
            bookings = page.bookings
            hasMore = page.hasMore ?? false
            nextOffset = page.nextOffset ?? page.bookings.count
        }
        isLoading = false
        // Offline with rows on screen is a staleness marker, not a failure.
        isStale = result.error == .offline && !bookings.isEmpty
        error = isStale || result.error == .cancelled ? nil : result.error
    }

    func loadMore() async {
        guard hasMore, !isLoadingMore else { return }
        isLoadingMore = true
        let asked = scope
        let result = await app.client.send(API.bookings(scope: asked.rawValue, limit: Self.page, offset: nextOffset))
        isLoadingMore = false
        guard asked == scope else { return }
        switch result {
        case .success(let page):
            // A booking made while she reads page one shifts every later row;
            // without this it would appear on both pages.
            let seen = Set(bookings.map(\.id))
            bookings += page.bookings.filter { !seen.contains($0.id) }
            hasMore = page.hasMore ?? false
            nextOffset = page.nextOffset ?? nextOffset + page.bookings.count
        case .failure(let failure):
            if failure != .cancelled { error = failure }
        }
    }
}

struct HistoryView: View {
    @Environment(\.strings) private var strings
    @State private var model: HistoryModel
    private let app: AppModel

    init(app: AppModel) {
        self.app = app
        _model = State(initialValue: HistoryModel(app: app))
    }

    var body: some View {
        VelroScreen(title: strings["history.title"]) {
            VStack(spacing: Spacing.md) {
                Picker("", selection: Binding(get: { model.scope }, set: { scope in Task { await model.show(scope) } })) {
                    Text(strings["history.scope.upcoming"]).tag(HistoryModel.Scope.upcoming)
                    Text(strings["history.scope.past"]).tag(HistoryModel.Scope.past)
                }
                .pickerStyle(.segmented)

                if model.isStale {
                    Text(strings["common.state.offline"])
                        .velroFont(.caption)
                        .foregroundStyle(Palette.onSurfaceVariant)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }

                list
            }
            .padding(.horizontal, Spacing.gutter)
            .padding(.top, Spacing.md)
        }
        .task { await model.show(.upcoming) }
    }

    @ViewBuilder
    private var list: some View {
        if model.isLoading {
            LoadingState()
        } else if let error = model.error, model.bookings.isEmpty {
            ErrorState(error: error) { Task { await model.refresh() } }
        } else if model.bookings.isEmpty {
            if model.scope == .upcoming {
                EmptyState(key: "empty.bookings", systemImage: "calendar", actionKey: "home.action.search") {
                    app.router.replaceAll(with: .ask)
                }
            } else {
                EmptyState(key: "history.empty.past", systemImage: "clock.arrow.circlepath")
            }
        } else {
            ScrollView {
                LazyVStack(spacing: Spacing.sm) {
                    ForEach(model.bookings) { booking in
                        Button { app.router.open(.booking(booking.id)) } label: { BookingCard(booking: booking) }
                            .buttonStyle(PressStyle())
                    }
                    if model.hasMore {
                        TextAction(label: strings["history.action.load_more"], enabled: !model.isLoadingMore) {
                            Task { await model.loadMore() }
                        }
                    }
                }
                .padding(.bottom, Spacing.xl)
            }
            .refreshable { await model.refresh() }
        }
    }
}
