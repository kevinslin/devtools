# Comodoro agent guide

Comodoro is a native SwiftUI/AppKit macOS menu-bar Pomodoro timer. Read the [implementation conversation](codex://threads/019f23e4-65cf-75f0-bf69-4fffdcac44b7) for the original product requirements, design iterations, screenshots, and verification history.

## Recommended workflow

```sh
cd /Users/kevinlin/code/devtools/apps/comodoro
./scripts/test.sh
./scripts/build-app.sh
open dist/Comodoro.app
```

Use `./scripts/test.sh` instead of invoking SwiftPM directly. The script selects the matching Xcode toolchain and keeps SwiftPM caches inside the project. Never run `npm run precommit` in this repository.

## Architecture

- `PomodoroStateMachine` owns deterministic work/break transitions and absolute deadlines.
- `TimerController` publishes live UI state, persists the running timer, records completed focus blocks, and dispatches sounds and notifications.
- `ComodoroAppDelegate` owns the `NSStatusItem`: left-click opens the timer popover; right-click opens the context menu with **History…**.
- `PomodoroStore` stores completed focus blocks in `~/Library/Application Support/Comodoro/history.sqlite3`.
- `HistoryView` renders monthly daily counts; `HistoryWindowController` presents it from the right-click menu.
- `MenuBarIconRenderer` produces one colored AppKit image containing the phase-colored center, phase glyph, and black remaining-time ring. Keep it as one rendered image because macOS flattens layered SwiftUI status-item labels.

## Behavioral invariants

- Keep work at 25 minutes and break at 5 minutes unless product requirements change.
- Count a Pomodoro when its work block completes and the break begins.
- Preserve `PomodoroEvent.occurredAt` so sleep/relaunch catch-up records the original completion day.
- Keep SQLite inserts idempotent; replayed transitions after a crash must not duplicate history.
- Keep the menu-bar indicator ring-only. The numerical countdown belongs inside the opened popover.
- Avoid default notification sounds when phase sounds are active, or users will hear two alerts.

## Verification

Run `./scripts/test.sh` after timer, history, persistence, menu-bar, or sound changes. Build and launch `dist/Comodoro.app` for notification identity and real menu-bar behavior; `swift run` is only a development shortcut.
