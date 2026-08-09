import AppKit

enum PhaseSoundCue: Equatable, Sendable {
    case breakChime
    case workDong
    case completionChime

    var systemSoundName: String {
        switch self {
        case .breakChime: "Glass"
        case .workDong: "Submarine"
        case .completionChime: "Hero"
        }
    }

    var volume: Float {
        switch self {
        case .breakChime: 0.5
        case .workDong: 0.72
        case .completionChime: 0.58
        }
    }

    static func cue(for transition: PomodoroTransition) -> Self {
        switch transition {
        case .breakStarted: .breakChime
        case .workStarted: .workDong
        case .setCompleted: .completionChime
        }
    }
}

@MainActor
final class SoundCoordinator {
    private var activeSound: NSSound?

    func play(for transition: PomodoroTransition) {
        let cue = PhaseSoundCue.cue(for: transition)
        guard let sound = NSSound(named: NSSound.Name(cue.systemSoundName)) else {
            NSSound.beep()
            return
        }

        activeSound?.stop()
        sound.volume = cue.volume
        activeSound = sound
        sound.play()
    }
}
