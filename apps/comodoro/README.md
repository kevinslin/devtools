# Comodoro

A Codex-inspired native macOS menu-bar Pomodoro timer: 25 minutes of focus, 5 minutes of rest, and a configurable set of 1–12 cycles.

The menu-bar icon and the large in-app countdown are wrapped in live progress rings. Each ring starts full and drains clockwise as the current focus or break phase counts down. The compact menu-bar indicator pairs a black progress ring with a green focus or blue break center; the numerical countdown appears inside the opened app.

Each completed 25-minute focus block is recorded in SQLite. Right-click the menu-bar indicator and choose **History…** to open a monthly calendar with per-day counts, monthly totals, active days, and the best day.

## Requirements

- macOS 14 or newer
- Apple Swift 6 toolchain (Xcode or Command Line Tools)

## Build and launch

```sh
cd /Users/kevinlin/code/devtools/apps/comodoro
./scripts/build-app.sh
open dist/Comodoro.app
```

The first time you start a session, macOS asks for notification permission. Comodoro sends a system notification whenever a break begins, the next focus block begins, or the full set completes. A gentle Glass chime marks breaks, a deeper Submarine tone marks returning to work, and a warm Hero chime marks a completed set.

## Development

```sh
./scripts/test.sh
swift run Comodoro
```

`swift run` is convenient during development when the active developer directory points at a matching Xcode toolchain. Launch the built `.app` bundle for reliable macOS notification identity and permission handling. The scripts automatically prefer `/Applications/Xcode.app` when it is installed.

## Design

- `PomodoroStateMachine` owns deterministic timing and transitions.
- `TimerController` drives wall-clock updates, persistence, and UI state.
- `NotificationCoordinator` owns macOS notification authorization and delivery.
- `SoundCoordinator` plays distinct native macOS cues for each phase transition.
- `PomodoroStore` records completed focus blocks in `~/Library/Application Support/Comodoro/history.sqlite3`.
- `HistoryView` and `HistoryWindowController` present the right-click calendar history experience.
- `ComodoroMenuView` presents the menu-bar interface and controls.

Running state is persisted in `UserDefaults`. Deadlines use absolute dates, so elapsed time remains correct when the Mac sleeps or the app is relaunched.

## Agent context

Future coding agents should read [AGENTS.md](AGENTS.md) before changing the project. The [Codex implementation conversation](codex://threads/019f23e4-65cf-75f0-bf69-4fffdcac44b7) preserves the original requirements, visual iterations, and verification context.
