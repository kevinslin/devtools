import AppKit
import Foundation
import Testing
@testable import Comodoro

struct PomodoroStateMachineTests {
    private let start = Date(timeIntervalSince1970: 1_000)

    @Test("A fresh timer starts a full work block")
    func freshTimer() {
        let timer = PomodoroStateMachine(totalCycles: 5)

        #expect(timer.phase == .work)
        #expect(timer.runState == .idle)
        #expect(timer.remaining == 25 * 60)
        #expect(timer.currentCycle == 1)
    }

    @Test("Pausing and resuming preserves elapsed time")
    func pauseAndResume() {
        var timer = PomodoroStateMachine(totalCycles: 3, workDuration: 100, breakDuration: 20)
        timer.start(at: start)
        timer.pause(at: start.addingTimeInterval(37))

        #expect(timer.runState == .paused)
        #expect(timer.remaining == 63)

        timer.start(at: start.addingTimeInterval(80))
        #expect(timer.displayedRemaining(at: start.addingTimeInterval(90)) == 53)
    }

    @Test("A work block transitions into a break")
    func workToBreak() {
        var timer = PomodoroStateMachine(totalCycles: 2, workDuration: 25, breakDuration: 5)
        timer.start(at: start)

        let events = timer.advance(at: start.addingTimeInterval(25))

        #expect(events.map(\.transition) == [.breakStarted(completedCycle: 1)])
        #expect(events.first?.occurredAt == start.addingTimeInterval(25))
        #expect(timer.phase == .rest)
        #expect(timer.completedCycles == 0)
        #expect(timer.remaining == 5)
    }

    @Test("The progress ring tracks time remaining and drains to zero")
    func remainingFraction() {
        var timer = PomodoroStateMachine(totalCycles: 1, workDuration: 100, breakDuration: 20)
        #expect(timer.fractionRemaining(at: start) == 1)

        timer.start(at: start)
        #expect(timer.fractionRemaining(at: start.addingTimeInterval(25)) == 0.75)

        timer.advance(at: start.addingTimeInterval(100))
        #expect(timer.fractionRemaining(at: start.addingTimeInterval(100)) == 1)

        timer.advance(at: start.addingTimeInterval(120))
        #expect(timer.fractionRemaining(at: start.addingTimeInterval(120)) == 0)
    }

    @Test("A late tick catches up across phases without losing wall-clock time")
    func catchesUpAfterSleep() {
        var timer = PomodoroStateMachine(totalCycles: 2, workDuration: 25, breakDuration: 5)
        timer.start(at: start)

        let events = timer.advance(at: start.addingTimeInterval(56))

        #expect(events.map(\.transition) == [
            .breakStarted(completedCycle: 1),
            .workStarted(cycle: 2),
            .breakStarted(completedCycle: 2),
        ])
        #expect(timer.phase == .rest)
        #expect(timer.completedCycles == 1)
        #expect(timer.remaining == 4)
    }

    @Test("The final break completes the configured set")
    func completesSet() {
        var timer = PomodoroStateMachine(totalCycles: 2, workDuration: 25, breakDuration: 5)
        timer.start(at: start)

        let events = timer.advance(at: start.addingTimeInterval(60))

        #expect(events.last?.transition == .setCompleted(totalCycles: 2))
        #expect(timer.phase == .complete)
        #expect(timer.runState == .complete)
        #expect(timer.completedCycles == 2)
        #expect(timer.remaining == 0)
    }

    @Test("A persisted running timer restores its absolute deadline")
    func persistenceRoundTrip() throws {
        var original = PomodoroStateMachine(totalCycles: 2, workDuration: 25, breakDuration: 5)
        original.start(at: start)

        let data = try JSONEncoder().encode(original)
        var restored = try JSONDecoder().decode(PomodoroStateMachine.self, from: data)
        let events = restored.advance(at: start.addingTimeInterval(31))

        #expect(events.map(\.transition) == [
            .breakStarted(completedCycle: 1),
            .workStarted(cycle: 2),
        ])
        #expect(restored.phase == .work)
        #expect(restored.currentCycle == 2)
        #expect(restored.remaining == 24)
    }

    @Test("Cycle configuration is clamped and locked during a running set")
    func cycleConfiguration() {
        var timer = PomodoroStateMachine(totalCycles: 99)
        #expect(timer.totalCycles == 12)

        timer.setTotalCycles(0)
        #expect(timer.totalCycles == 1)

        timer.start(at: start)
        timer.setTotalCycles(7)
        #expect(timer.totalCycles == 1)
    }

    @Test("Phase transitions select distinct system sounds")
    func phaseSounds() {
        #expect(PhaseSoundCue.cue(for: .breakStarted(completedCycle: 1)).systemSoundName == "Glass")
        #expect(PhaseSoundCue.cue(for: .workStarted(cycle: 2)).systemSoundName == "Submarine")
        #expect(PhaseSoundCue.cue(for: .setCompleted(totalCycles: 2)).systemSoundName == "Hero")
    }

    @MainActor
    @Test("The menu-bar indicator uses phase-colored centers and black progress rings")
    func menuBarIconRendering() throws {
        let workImage = MenuBarIconRenderer.image(
            symbolName: "terminal.fill",
            fractionRemaining: 1,
            phase: .work
        )
        let restImage = MenuBarIconRenderer.image(
            symbolName: "cup.and.saucer.fill",
            fractionRemaining: 1,
            phase: .rest
        )

        #expect(workImage.size == NSSize(width: 18, height: 18))
        #expect(!workImage.isTemplate)
        #expect(!restImage.isTemplate)

        let workData = try #require(workImage.tiffRepresentation)
        let restData = try #require(restImage.tiffRepresentation)
        let workBitmap = try #require(NSBitmapImageRep(data: workData))
        let restBitmap = try #require(NSBitmapImageRep(data: restData))
        let workRing = try #require(workBitmap.colorAt(x: 9, y: 1)?.usingColorSpace(.deviceRGB))
        let restRing = try #require(restBitmap.colorAt(x: 9, y: 1)?.usingColorSpace(.deviceRGB))
        let workCenter = try #require(workBitmap.colorAt(x: 9, y: 4)?.usingColorSpace(.deviceRGB))
        let restCenter = try #require(restBitmap.colorAt(x: 9, y: 4)?.usingColorSpace(.deviceRGB))

        #expect(workRing.redComponent < 0.1)
        #expect(workRing.greenComponent < 0.1)
        #expect(workRing.blueComponent < 0.1)
        #expect(restRing.redComponent < 0.1)
        #expect(restRing.greenComponent < 0.1)
        #expect(restRing.blueComponent < 0.1)
        #expect(workCenter.greenComponent > workCenter.blueComponent)
        #expect(restCenter.blueComponent > restCenter.greenComponent)
    }
}
