# claw-debug

`claw-debug` dumps local OpenClaw debug files for a single session key.

## Quickstart

```sh
claw-debug dump
claw-debug dump agent:main:main
```

## Build

Run `npm run build` from the repository root to compile
`tools/claw-debug/src/claw-debug.ts` into `tools/claw-debug/bin/claw-debug`. The existing
`bin/claw-debug` command remains available through a symlink.

## Command

```sh
claw-debug dump [session-key]
```

## Arguments

- `session-key`: OpenClaw session key to dump. Defaults to `agent:main:main`.

## Session Key Examples

The main agent session uses:

```sh
claw-debug dump agent:main:main
```

When the TUI status bar shows `agent main | session main (kevin)`, it is attached to the main session, so use:

```sh
claw-debug dump agent:main:main
```

Standalone TUI-created sessions use a UUID suffix:

```sh
claw-debug dump agent:main:tui-f1c0722c-a3f5-4289-a005-dd5959aed287
```

Slack direct-message sessions use the lowercased Slack user id:

```sh
claw-debug dump agent:main:slack:direct:u04hrd671t2
```

Slack channel sessions use the lowercased Slack channel id:

```sh
claw-debug dump agent:main:slack:channel:c04hebbnb25
```

Slack slash-command sessions use the lowercased Slack user id:

```sh
claw-debug dump agent:main:slack:slash:u04hrd671t2
```

## Data Sources

The CLI reads from `~/.openclaw` by default. Set `OPENCLAW_HOME` to point at another state root.

For the selected session, it prints the relevant files it can find:

- session summary from `agents/<agent>/sessions/sessions.json`, narrowed to the requested key
- session JSONL
- trajectory pointer JSON
- trajectory JSONL
- Codex app server JSON
- Codex rollout JSONL matching the app-server thread id

Missing optional files are shown as `[missing]` with the location that was checked.
