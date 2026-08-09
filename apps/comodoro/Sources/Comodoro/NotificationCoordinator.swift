import Foundation
import UserNotifications

final class NotificationCoordinator: NSObject, UNUserNotificationCenterDelegate, @unchecked Sendable {
    private let center = UNUserNotificationCenter.current()

    override init() {
        super.init()
        center.delegate = self
    }

    func requestAuthorization() {
        center.requestAuthorization(options: [.alert, .sound]) { _, _ in }
    }

    func notify(_ transition: PomodoroTransition, totalCycles: Int) {
        let content = UNMutableNotificationContent()

        switch transition {
        case let .breakStarted(completedCycle):
            content.title = "Break unlocked"
            content.body = "Focus block \(completedCycle) of \(totalCycles) complete. Take five."
        case let .workStarted(cycle):
            content.title = "Focus mode"
            content.body = "Cycle \(cycle) of \(totalCycles) starts now."
        case let .setCompleted(totalCycles):
            content.title = "Pomodoro set complete"
            content.body = "All \(totalCycles) focus cycles are done. Nice work."
        }

        let request = UNNotificationRequest(
            identifier: UUID().uuidString,
            content: content,
            trigger: nil
        )
        center.add(request)
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner]
    }
}
