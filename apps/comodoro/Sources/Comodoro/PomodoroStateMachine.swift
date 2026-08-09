import Foundation

enum PomodoroPhase: String, Codable, Equatable, Sendable {
    case work
    case rest
    case complete
}

enum PomodoroRunState: String, Codable, Equatable, Sendable {
    case idle
    case running
    case paused
    case complete
}

enum PomodoroTransition: Equatable, Sendable {
    case breakStarted(completedCycle: Int)
    case workStarted(cycle: Int)
    case setCompleted(totalCycles: Int)
}

struct PomodoroEvent: Equatable, Sendable {
    let transition: PomodoroTransition
    let occurredAt: Date
}

struct PomodoroStateMachine: Codable, Equatable, Sendable {
    static let defaultWorkDuration: TimeInterval = 25 * 60
    static let defaultBreakDuration: TimeInterval = 5 * 60
    static let cycleRange = 1...12

    private(set) var phase: PomodoroPhase
    private(set) var runState: PomodoroRunState
    private(set) var totalCycles: Int
    private(set) var completedCycles: Int
    private(set) var remaining: TimeInterval
    private(set) var deadline: Date?

    let workDuration: TimeInterval
    let breakDuration: TimeInterval

    init(
        totalCycles: Int = 5,
        workDuration: TimeInterval = Self.defaultWorkDuration,
        breakDuration: TimeInterval = Self.defaultBreakDuration
    ) {
        self.totalCycles = Self.cycleRange.clamped(totalCycles)
        self.workDuration = max(1, workDuration)
        self.breakDuration = max(1, breakDuration)
        phase = .work
        runState = .idle
        completedCycles = 0
        remaining = max(1, workDuration)
        deadline = nil
    }

    var currentCycle: Int {
        min(completedCycles + 1, totalCycles)
    }

    var isConfigurable: Bool {
        runState == .idle || runState == .complete
    }

    mutating func setTotalCycles(_ cycles: Int) {
        guard isConfigurable else { return }
        totalCycles = Self.cycleRange.clamped(cycles)
        if runState == .complete {
            reset()
        }
    }

    mutating func start(at date: Date) {
        if runState == .complete {
            reset()
        }
        guard runState == .idle || runState == .paused else { return }
        runState = .running
        deadline = date.addingTimeInterval(remaining)
    }

    mutating func pause(at date: Date) {
        guard runState == .running else { return }
        remaining = displayedRemaining(at: date)
        deadline = nil
        runState = .paused
    }

    mutating func reset() {
        phase = .work
        runState = .idle
        completedCycles = 0
        remaining = workDuration
        deadline = nil
    }

    func displayedRemaining(at date: Date) -> TimeInterval {
        guard runState == .running, let deadline else {
            return remaining
        }
        return max(0, deadline.timeIntervalSince(date))
    }

    func fractionRemaining(at date: Date) -> Double {
        let duration: TimeInterval
        switch phase {
        case .work:
            duration = workDuration
        case .rest:
            duration = breakDuration
        case .complete:
            return 0
        }

        guard duration > 0 else { return 0 }
        return Swift.min(Swift.max(displayedRemaining(at: date) / duration, 0), 1)
    }

    @discardableResult
    mutating func advance(at date: Date) -> [PomodoroEvent] {
        guard runState == .running, var nextDeadline = deadline else { return [] }

        var events: [PomodoroEvent] = []
        while date >= nextDeadline, runState == .running {
            switch phase {
            case .work:
                phase = .rest
                remaining = breakDuration
                events.append(
                    PomodoroEvent(
                        transition: .breakStarted(completedCycle: completedCycles + 1),
                        occurredAt: nextDeadline
                    )
                )
                nextDeadline = nextDeadline.addingTimeInterval(breakDuration)

            case .rest:
                completedCycles += 1
                if completedCycles >= totalCycles {
                    phase = .complete
                    runState = .complete
                    remaining = 0
                    deadline = nil
                    events.append(
                        PomodoroEvent(
                            transition: .setCompleted(totalCycles: totalCycles),
                            occurredAt: nextDeadline
                        )
                    )
                    return events
                }

                phase = .work
                remaining = workDuration
                events.append(
                    PomodoroEvent(
                        transition: .workStarted(cycle: completedCycles + 1),
                        occurredAt: nextDeadline
                    )
                )
                nextDeadline = nextDeadline.addingTimeInterval(workDuration)

            case .complete:
                runState = .complete
                remaining = 0
                deadline = nil
                return events
            }
        }

        deadline = nextDeadline
        remaining = max(0, nextDeadline.timeIntervalSince(date))
        return events
    }
}

private extension ClosedRange where Bound == Int {
    func clamped(_ value: Int) -> Int {
        Swift.min(Swift.max(value, lowerBound), upperBound)
    }
}
