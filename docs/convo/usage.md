# convo

<div align="center"><img src="../../assets/convo-logo.png" alt="Conversation search mascot" width="120" /></div>

`convo` is a CLI for managing Codex conversations.
The first supported command is `search`, which does a fast regex search over local Codex session logs.

## Quickstart

```sh
convo search "<query>"
```

## Command

```sh
convo search <query> [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--format json|markdown]
```

## Arguments

- `query`: regex pattern to search for in conversation JSONL lines.

## Options

- `--from`: optional inclusive start date (`YYYY-MM-DD`).
- `--to`: optional inclusive end date (`YYYY-MM-DD`).
- `--format`: `markdown|json` (default: `markdown`).

## Data sources

- Active sessions root: `~/.codex/sessions`
- Archived sessions root: `~/.codex/archived_sessions`

Override with:

- `CONVO_SESSIONS_ROOT`
- `CONVO_ARCHIVED_ROOT`

## Markdown output format

The default markdown format is:

```md
### [description of session]
- absolute path: [string]
- sessionid: [string]
- created: [date]
- updated: [date]

[query result and surrounding context]
```

Each matched session includes one or more surrounding-context blocks (line-numbered).

## Examples

```sh
# default markdown output
convo search "request_id"

# narrow by date
convo search "TOO_MANY_ROWS" --from 2026-03-01 --to 2026-03-06

# machine-readable output
convo search "session_meta" --format json
```
