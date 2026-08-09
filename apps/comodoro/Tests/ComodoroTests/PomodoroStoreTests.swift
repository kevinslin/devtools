import Foundation
import Testing
@testable import Comodoro

@MainActor
struct PomodoroStoreTests {
    @Test("Completed pomodoros are grouped by local calendar day")
    func dailyCounts() throws {
        let databaseURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("comodoro-store-\(UUID().uuidString).sqlite3")
        let store = PomodoroStore(databaseURL: databaseURL)

        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try #require(TimeZone(secondsFromGMT: 0))
        let julySecond = try #require(
            calendar.date(from: DateComponents(year: 2026, month: 7, day: 2, hour: 9))
        )
        let julyThird = try #require(calendar.date(byAdding: .day, value: 1, to: julySecond))

        store.recordCompletedPomodoro(at: julySecond, duration: 1_500, cycle: 1, totalCycles: 3)
        store.recordCompletedPomodoro(
            at: julySecond.addingTimeInterval(3_600),
            duration: 1_500,
            cycle: 2,
            totalCycles: 3
        )
        store.recordCompletedPomodoro(at: julyThird, duration: 1_500, cycle: 3, totalCycles: 3)

        let counts = store.dailyCounts(in: julySecond, calendar: calendar)
        #expect(counts[calendar.startOfDay(for: julySecond)] == 2)
        #expect(counts[calendar.startOfDay(for: julyThird)] == 1)
        #expect(counts.values.reduce(0, +) == 3)
        #expect(store.errorMessage == nil)
    }

    @Test("Replayed completion events are stored only once")
    func duplicateProtection() {
        let databaseURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("comodoro-dedup-\(UUID().uuidString).sqlite3")
        let store = PomodoroStore(databaseURL: databaseURL)
        let completion = Date(timeIntervalSince1970: 1_800_000_000)

        store.recordCompletedPomodoro(at: completion, duration: 1_500, cycle: 1, totalCycles: 1)
        store.recordCompletedPomodoro(at: completion, duration: 1_500, cycle: 1, totalCycles: 1)

        let counts = store.dailyCounts(in: completion)
        #expect(counts.values.reduce(0, +) == 1)
        #expect(store.revision == 1)
    }
}
