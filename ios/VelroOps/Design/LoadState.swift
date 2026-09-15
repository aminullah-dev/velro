import SwiftUI
import VelroCore

/// A screen's answer: not here yet, here, or failed.
///
///     @State private var state: LoadState<DashboardSnapshot> = .loading
///     ...
///     state = LoadState(await ops.send(AdminAPI.dashboard()), keeping: state)
enum LoadState<Value> {
    case loading
    case loaded(Value)
    case failed(APIError)

    /// A new answer. A failed refresh keeps what was already on screen --
    /// the offline banner says it may be old -- rather than blanking it.
    init(_ result: Result<Value, APIError>, keeping previous: LoadState<Value>? = nil) {
        switch result {
        case .success(let value):
            self = .loaded(value)
        case .failure(let error):
            if let previous, case .loaded = previous {
                self = previous
            } else {
                self = .failed(error)
            }
        }
    }

    var value: Value? {
        if case .loaded(let value) = self { value } else { nil }
    }

    var error: APIError? {
        if case .failed(let error) = self { error } else { nil }
    }

    var isLoading: Bool {
        if case .loading = self { true } else { false }
    }
}

/// Loading, the error with a retry, or the content.
///
///     LoadStateView(state, retry: { await model.load() }) { snapshot in
///         DashboardContent(snapshot: snapshot)
///     }
struct LoadStateView<Value, Content: View>: View {
    private let state: LoadState<Value>
    private let retry: (@MainActor () async -> Void)?
    private let content: (Value) -> Content

    init(_ state: LoadState<Value>, retry: (@MainActor () async -> Void)? = nil,
         @ViewBuilder content: @escaping (Value) -> Content) {
        self.state = state
        self.retry = retry
        self.content = content
    }

    var body: some View {
        switch state {
        case .loading: LoadingView()
        case .failed(let error): ErrorView(error: error, retry: retry)
        case .loaded(let value): content(value)
        }
    }
}
