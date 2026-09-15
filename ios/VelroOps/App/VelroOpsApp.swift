import SwiftUI

/// VELRO Ops: the operations console, on iPhone, iPad and Mac.
///
/// A SwiftUI `App` rather than the phone apps' UIKit host: this one has no
/// brand-green screen whose status bar needs turning light, and it has to run
/// on the Mac, where there is no UIKit to host it.
@main
struct VelroOpsApp: App {
    @State private var ops = OpsModel.live()

    var body: some Scene {
        #if os(macOS)
        WindowGroup {
            RootView()
                .environment(ops)
                .frame(minWidth: 860, minHeight: 560)
        }
        .defaultSize(width: 1280, height: 820)
        .commands { SidebarCommands() }
        #else
        WindowGroup {
            RootView()
                .environment(ops)
        }
        #endif
    }
}
