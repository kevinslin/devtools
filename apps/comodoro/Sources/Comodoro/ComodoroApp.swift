import AppKit
import Combine
import SwiftUI

@main
struct ComodoroApp: App {
    @NSApplicationDelegateAdaptor(ComodoroAppDelegate.self) private var appDelegate

    var body: some Scene {
        Settings {
            EmptyView()
        }
    }
}

@MainActor
final class ComodoroAppDelegate: NSObject, NSApplicationDelegate {
    private let store: PomodoroStore
    private let timer: TimerController
    private let popover = NSPopover()
    private let historyWindow = HistoryWindowController()

    private var statusItem: NSStatusItem?
    private var cancellables = Set<AnyCancellable>()

    override init() {
        let store = PomodoroStore()
        self.store = store
        timer = TimerController(store: store)
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApplication.shared.setActivationPolicy(.accessory)
        configurePopover()
        configureStatusItem()

        timer.$now
            .sink { [weak self] _ in self?.refreshStatusItem() }
            .store(in: &cancellables)

        if ProcessInfo.processInfo.arguments.contains("--show-history") {
            DispatchQueue.main.async { [weak self] in self?.showHistory() }
        }
    }

    private func configurePopover() {
        popover.behavior = .transient
        popover.animates = true
        popover.contentSize = NSSize(width: 340, height: 530)
        popover.contentViewController = NSHostingController(
            rootView: ComodoroMenuView().environmentObject(timer)
        )
    }

    private func configureStatusItem() {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        guard let button = item.button else { return }
        button.target = self
        button.action = #selector(statusItemClicked(_:))
        button.sendAction(on: [.leftMouseUp, .rightMouseUp])
        button.imagePosition = .imageOnly
        statusItem = item
        refreshStatusItem()
    }

    private func refreshStatusItem() {
        guard let button = statusItem?.button else { return }
        button.image = MenuBarIconRenderer.image(
            symbolName: timer.menuBarSymbol,
            fractionRemaining: timer.remainingFraction,
            phase: timer.model.phase
        )
        button.image?.accessibilityDescription = "Comodoro, \(timer.menuBarTitle) remaining"
        button.toolTip = "Comodoro • \(timer.menuBarTitle)"
    }

    @objc private func statusItemClicked(_ sender: NSStatusBarButton) {
        if NSApplication.shared.currentEvent?.type == .rightMouseUp {
            showContextMenu(from: sender)
        } else {
            togglePopover(from: sender)
        }
    }

    private func togglePopover(from button: NSStatusBarButton) {
        if popover.isShown {
            popover.performClose(nil)
        } else {
            popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
        }
    }

    private func showContextMenu(from button: NSStatusBarButton) {
        guard let event = NSApplication.shared.currentEvent else { return }
        let menu = NSMenu(title: "Comodoro")

        let historyItem = NSMenuItem(
            title: "History…",
            action: #selector(showHistory),
            keyEquivalent: ""
        )
        historyItem.image = NSImage(systemSymbolName: "calendar", accessibilityDescription: nil)
        historyItem.target = self
        menu.addItem(historyItem)

        menu.addItem(.separator())

        let quitItem = NSMenuItem(
            title: "Quit Comodoro",
            action: #selector(quitApplication),
            keyEquivalent: "q"
        )
        quitItem.target = self
        menu.addItem(quitItem)

        NSMenu.popUpContextMenu(menu, with: event, for: button)
    }

    @objc private func showHistory() {
        popover.performClose(nil)
        historyWindow.show(store: store)
    }

    @objc private func quitApplication() {
        NSApplication.shared.terminate(nil)
    }
}
