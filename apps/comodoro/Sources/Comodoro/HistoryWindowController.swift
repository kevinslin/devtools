import AppKit
import SwiftUI

@MainActor
final class HistoryWindowController {
    private var window: NSWindow?

    func show(store: PomodoroStore) {
        if window == nil {
            let historyView = HistoryView(store: store)
            let hostingController = NSHostingController(rootView: historyView)
            let window = NSWindow(contentViewController: hostingController)
            window.title = "Comodoro History"
            window.styleMask = [.titled, .closable, .miniaturizable]
            window.setContentSize(NSSize(width: 560, height: 610))
            window.minSize = NSSize(width: 500, height: 560)
            window.isReleasedWhenClosed = false
            window.center()
            self.window = window
        }

        NSApplication.shared.activate(ignoringOtherApps: true)
        window?.makeKeyAndOrderFront(nil)
        window?.orderFrontRegardless()
    }
}
