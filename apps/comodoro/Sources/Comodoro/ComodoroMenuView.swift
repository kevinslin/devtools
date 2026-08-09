import AppKit
import SwiftUI

struct ComodoroMenuView: View {
    @EnvironmentObject private var timer: TimerController

    private let accent = Color(red: 0.09, green: 0.72, blue: 0.57)
    private let surface = Color(red: 0.055, green: 0.063, blue: 0.071)
    private let panel = Color.white.opacity(0.055)

    var body: some View {
        VStack(spacing: 0) {
            header

            VStack(spacing: 18) {
                timerRing
                cycleTrack
                controls
                configuration
            }
            .padding(.horizontal, 20)
            .padding(.bottom, 18)

            footer
        }
        .frame(width: 340)
        .background(surface)
        .foregroundStyle(.white)
    }

    private var header: some View {
        HStack(spacing: 10) {
            ZStack {
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .fill(accent.opacity(0.16))
                Image(systemName: "chevron.left.forwardslash.chevron.right")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(accent)
            }
            .frame(width: 30, height: 30)

            VStack(alignment: .leading, spacing: 1) {
                Text("COMODORO")
                    .font(.system(size: 13, weight: .bold, design: .monospaced))
                    .tracking(1.4)
                Text("CODE • FOCUS • SHIP")
                    .font(.system(size: 9, weight: .medium, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .tracking(0.8)
            }

            Spacer()

            phaseBadge
        }
        .padding(16)
    }

    private var phaseBadge: some View {
        HStack(spacing: 5) {
            Circle()
                .fill(phaseColor)
                .frame(width: 6, height: 6)
                .shadow(color: phaseColor.opacity(0.8), radius: 4)
            Text(phaseTitle.uppercased())
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .tracking(0.6)
        }
        .foregroundStyle(phaseColor)
        .padding(.horizontal, 9)
        .padding(.vertical, 6)
        .background(phaseColor.opacity(0.11), in: Capsule())
        .overlay(Capsule().stroke(phaseColor.opacity(0.22), lineWidth: 1))
    }

    private var timerRing: some View {
        ZStack {
            Circle()
                .stroke(Color.white.opacity(0.07), lineWidth: 9)
            Circle()
                .trim(from: 0, to: timer.remainingFraction)
                .stroke(
                    AngularGradient(
                        colors: [phaseColor.opacity(0.45), phaseColor],
                        center: .center
                    ),
                    style: StrokeStyle(lineWidth: 9, lineCap: .round)
                )
                .rotationEffect(.degrees(-90))
                .shadow(color: phaseColor.opacity(0.35), radius: 7)
                .animation(.linear(duration: 0.2), value: timer.remainingFraction)

            VStack(spacing: 7) {
                Text(timer.formattedRemaining)
                    .font(.system(size: 41, weight: .medium, design: .monospaced))
                    .monospacedDigit()
                    .contentTransition(.numericText())
                Text(phaseSubtitle)
                    .font(.system(size: 10, weight: .semibold, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .tracking(1.2)
            }
        }
        .frame(width: 184, height: 184)
        .padding(.vertical, 2)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(phaseTitle), \(timer.formattedRemaining) remaining")
    }

    private var cycleTrack: some View {
        HStack(spacing: 12) {
            Text("CYCLES")
                .font(.system(size: 9, weight: .bold, design: .monospaced))
                .foregroundStyle(.secondary)
                .tracking(1)

            HStack(spacing: 6) {
                ForEach(0..<timer.model.totalCycles, id: \.self) { index in
                    Capsule()
                        .fill(cycleColor(at: index))
                        .frame(width: index == timer.model.completedCycles && timer.model.runState != .complete ? 18 : 7, height: 7)
                        .animation(.spring(response: 0.3), value: timer.model.completedCycles)
                }
            }

            Spacer()

            Text(timer.cycleLabel)
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundStyle(accent)
        }
        .padding(.horizontal, 2)
    }

    private var controls: some View {
        HStack(spacing: 10) {
            Button(action: primaryAction) {
                Label(primaryButtonTitle, systemImage: primaryButtonIcon)
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(PrimaryButtonStyle(color: accent))

            Button(action: timer.reset) {
                Image(systemName: "arrow.counterclockwise")
                    .frame(width: 40, height: 18)
            }
            .buttonStyle(SecondaryButtonStyle())
            .help("Reset current set")
        }
    }

    private var configuration: some View {
        HStack {
            VStack(alignment: .leading, spacing: 3) {
                Text("SET LENGTH")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundStyle(.secondary)
                    .tracking(1)
                Text("25 min focus  /  5 min break")
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
            }

            Spacer()

            HStack(spacing: 10) {
                cycleButton(icon: "minus", delta: -1)
                Text("\(timer.model.totalCycles)")
                    .font(.system(size: 15, weight: .bold, design: .monospaced))
                    .frame(minWidth: 17)
                cycleButton(icon: "plus", delta: 1)
            }
            .opacity(timer.model.isConfigurable ? 1 : 0.38)
        }
        .padding(12)
        .background(panel, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.white.opacity(0.06), lineWidth: 1)
        )
    }

    private var footer: some View {
        HStack {
            Label("Chimes + notifications on phase change", systemImage: "bell.badge")
                .font(.system(size: 9, weight: .medium, design: .monospaced))
                .foregroundStyle(.secondary)

            Spacer()

            Button("Quit") {
                NSApplication.shared.terminate(nil)
            }
            .buttonStyle(.plain)
            .font(.system(size: 10, weight: .semibold, design: .monospaced))
            .foregroundStyle(.secondary)
        }
        .padding(.horizontal, 18)
        .padding(.vertical, 12)
        .background(Color.black.opacity(0.22))
        .overlay(alignment: .top) {
            Rectangle().fill(Color.white.opacity(0.06)).frame(height: 1)
        }
    }

    private func cycleButton(icon: String, delta: Int) -> some View {
        Button {
            timer.setCycles(timer.model.totalCycles + delta)
        } label: {
            Image(systemName: icon)
                .font(.system(size: 10, weight: .bold))
                .frame(width: 25, height: 25)
                .background(Color.white.opacity(0.07), in: Circle())
        }
        .buttonStyle(.plain)
        .disabled(!timer.model.isConfigurable)
    }

    private func cycleColor(at index: Int) -> Color {
        if timer.model.runState == .complete || index < timer.model.completedCycles {
            return accent
        }
        if index == timer.model.completedCycles {
            return phaseColor.opacity(0.85)
        }
        return Color.white.opacity(0.12)
    }

    private func primaryAction() {
        switch timer.model.runState {
        case .running:
            timer.pause()
        case .idle, .paused, .complete:
            timer.start()
        }
    }

    private var primaryButtonTitle: String {
        switch timer.model.runState {
        case .running: "Pause"
        case .paused: "Resume"
        case .complete: "Start new set"
        case .idle: "Start focus"
        }
    }

    private var primaryButtonIcon: String {
        timer.model.runState == .running ? "pause.fill" : "play.fill"
    }

    private var phaseTitle: String {
        switch timer.model.phase {
        case .work: "Focus"
        case .rest: "Break"
        case .complete: "Done"
        }
    }

    private var phaseSubtitle: String {
        switch timer.model.runState {
        case .idle: "READY TO FOCUS"
        case .paused: "SESSION PAUSED"
        case .complete: "SET COMPLETE"
        case .running: timer.model.phase == .rest ? "RECOVERY WINDOW" : "DEEP WORK"
        }
    }

    private var phaseColor: Color {
        Color(nsColor: timer.model.phase.displayColor)
    }
}

private struct PrimaryButtonStyle: ButtonStyle {
    let color: Color

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 12, weight: .bold, design: .monospaced))
            .foregroundStyle(Color(red: 0.02, green: 0.10, blue: 0.08))
            .padding(.vertical, 11)
            .background(color.opacity(configuration.isPressed ? 0.75 : 1), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .scaleEffect(configuration.isPressed ? 0.985 : 1)
    }
}

private struct SecondaryButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .foregroundStyle(.white.opacity(configuration.isPressed ? 0.55 : 0.82))
            .padding(.vertical, 11)
            .background(Color.white.opacity(0.07), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .stroke(Color.white.opacity(0.08), lineWidth: 1)
            )
    }
}
