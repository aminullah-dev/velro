import SwiftUI

/// Runs an action now and then every `interval` while the view is on
/// screen, and stops when it goes away or the app goes to the background.
///
/// The dashboard refreshes every half minute, as the panel's does; the live
/// map faster. One request at a time: the next waits for the last to finish,
/// so a slow connection never piles requests up.
///
///     .poll(every: .seconds(30)) { [model] in await model.load() }
///
/// On the Mac a window in the background of another app keeps refreshing --
/// a console left open on a second screen is the normal case -- and only a
/// hidden app stops.
struct Poller: ViewModifier {
    let interval: Duration
    let action: @MainActor @Sendable () async -> Void
    @Environment(\.scenePhase) private var scenePhase

    func body(content: Content) -> some View {
        let running = scenePhase != .background
        let interval = interval
        let action = action
        return content.task(id: running) {
            guard running else { return }
            while !Task.isCancelled {
                await action()
                do {
                    try await Task.sleep(for: interval)
                } catch {
                    return
                }
            }
        }
    }
}

extension View {
    func poll(every interval: Duration, perform action: @escaping @MainActor @Sendable () async -> Void) -> some View {
        modifier(Poller(interval: interval, action: action))
    }
}
