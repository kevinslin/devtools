import Combine
import Foundation

@MainActor
final class TimerController: ObservableObject {
    @Published private(set) var model: PomodoroStateMachine
    @Published private(set) var now = Date()

    private static let persistenceKey = "comodoro.timer-state.v1"

    private let notifications: NotificationCoordinator
    private let sounds: SoundCoordinator
    private let store: PomodoroStore
    private let defaults: UserDefaults
    private var ticker: AnyCancellable?

    init(
        defaults: UserDefaults = .standard,
        notifications: NotificationCoordinator = NotificationCoordinator(),
        sounds: SoundCoordinator = SoundCoordinator(),
        store: PomodoroStore = PomodoroStore()
    ) {
        self.defaults = defaults
        self.notifications = notifications
        self.sounds = sounds
        self.store = store

        if
            let data = defaults.data(forKey: Self.persistenceKey),
            let restored = try? JSONDecoder().decode(PomodoroStateMachine.self, from: data)
        {
            model = restored
        } else {
            model = PomodoroStateMachine()
        }

        now = Date()
        let restoredEvents = model.advance(at: now)
        if !restoredEvents.isEmpty {
            recordCompletedPomodoros(from: restoredEvents)
            persist()
        }

        ticker = Timer.publish(every: 0.2, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] date in
                self?.update(at: date)
            }
    }

    var remaining: TimeInterval {
        model.displayedRemaining(at: now)
    }

    var remainingFraction: Double {
        model.fractionRemaining(at: now)
    }

    var menuBarTitle: String {
        switch model.runState {
        case .running, .paused:
            return formattedRemaining
        case .complete:
            return "Done"
        case .idle:
            return "Focus"
        }
    }

    var menuBarSymbol: String {
        switch model.phase {
        case .work: "terminal.fill"
        case .rest: "cup.and.saucer.fill"
        case .complete: "checkmark.seal.fill"
        }
    }

    var formattedRemaining: String {
        let seconds = max(0, Int(ceil(remaining)))
        return String(format: "%02d:%02d", seconds / 60, seconds % 60)
    }

    var cycleLabel: String {
        if model.runState == .complete {
            return "\(model.totalCycles) / \(model.totalCycles)"
        }
        return "\(model.currentCycle) / \(model.totalCycles)"
    }

    func setCycles(_ cycles: Int) {
        model.setTotalCycles(cycles)
        persist()
    }

    func start() {
        notifications.requestAuthorization()
        model.start(at: Date())
        now = Date()
        persist()
    }

    func pause() {
        let date = Date()
        model.pause(at: date)
        now = date
        persist()
    }

    func reset() {
        model.reset()
        now = Date()
        persist()
    }

    private func update(at date: Date) {
        now = date
        let events = model.advance(at: date)
        guard !events.isEmpty else { return }
        recordCompletedPomodoros(from: events)
        persist()
        events.forEach {
            sounds.play(for: $0.transition)
            notifications.notify($0.transition, totalCycles: model.totalCycles)
        }
    }

    private func recordCompletedPomodoros(from events: [PomodoroEvent]) {
        events.forEach { event in
            guard case let .breakStarted(completedCycle) = event.transition else { return }
            store.recordCompletedPomodoro(
                at: event.occurredAt,
                duration: model.workDuration,
                cycle: completedCycle,
                totalCycles: model.totalCycles
            )
        }
    }

    private func persist() {
        guard let data = try? JSONEncoder().encode(model) else { return }
        defaults.set(data, forKey: Self.persistenceKey)
    }
}
