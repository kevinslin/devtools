# Tokemon

Tokemon is a local CLI for reporting token usage from Codex and Claude session logs. Its JSON output is also used as the data backend for the Tokemon macOS menu-bar app.
Codex queries maintain a persistent on-disk index so repeated runs can reuse unchanged session data instead of replaying the same raw logs.

## Quickstart

```sh
# default: current_week, hourly buckets, csv, provider=codex
tokemon
```

## Menu app

Build and open the native menu-bar app with:

```sh
bin/tokemon-menuapp
```

The menu app opens from the macOS menu bar, stays open until you click the icon again, and supports:

- `Today`: hourly token totals
- `Week`: daily token totals across the last 7 days
- `Month`: weekly token totals across the trailing month window
- `Year`: monthly token totals across the last 12 calendar months
- recent snapshot caching: the last loaded totals render immediately on reopen or range toggles while a background refresh updates them

## Command

```sh
tokemon [range] [--sum-by N|daily|weekly|monthly] [--group-by none|workspace|session|provider] [--format csv|json] [--provider codex|claude|all]
```

## Arguments

- `range`:
  - Presets:
    - `current_week`: current Sunday-start week window
    - `week`: trailing 7 days relative to now
    - `month`: trailing 1 calendar month relative to now
    - `year`: trailing 12 calendar months relative to now
  - Explicit date range: `YYYY-MM-DD YYYY-MM-DD` (inclusive end date)

## Options

- `--sum-by`: bucket size by minutes (for example `15`, `60`) or presets `daily|weekly|monthly` (default: `60`)
- `--group-by`: `none|workspace|session|provider` (default: `none`)
- `--format`: `csv|json` (default: `csv`)
- `--provider`: `codex|claude|all` (default: `codex`)

## Examples

```sh
# monthly token usage from codex
tokemon month --sum-by monthly

# this week, grouped by workspace
tokemon current_week --group-by workspace

# combine codex + claude and group by provider
tokemon current_week --provider all --group-by provider --format csv

# combine codex + claude and group by session
tokemon current_week --provider all --group-by session --format csv

# explicit date range, 30-minute buckets, json output
tokemon 2026-02-01 2026-02-15 --sum-by 30 --format json --provider all
```

## Data sources

- Codex:
  - `~/.codex/sessions/**/*.jsonl`
  - `~/.codex/archived_sessions/*.jsonl`
- Claude:
  - `~/.claude/projects/**/*.jsonl`

For explicit Codex date ranges, Tokemon prunes session discovery to the matching `~/.codex/sessions/YYYY/MM/DD` folders plus the prior spillover day when that standard date-based layout is present.
The first Codex query against a given set of files populates the index; later queries reuse unchanged files and rescan only paths whose size or mtime changed.
Codex session files that replay the same `session_meta.payload.id` are reconciled against that session's highest cumulative totals so resumed/snapshotted files do not double count token usage.

## Environment overrides

- `TOKEMON_CODEX_SESSIONS_ROOT`
- `TOKEMON_CODEX_ARCHIVED_ROOT`
- `TOKEMON_CLAUDE_PROJECTS_ROOT`
- `TOKEMON_INDEX_PATH`: override the SQLite index path (default: `~/Library/Caches/tokemon/index.sqlite3` on macOS, `XDG_CACHE_HOME/tokemon/index.sqlite3` or `~/.cache/tokemon/index.sqlite3` elsewhere)
- `TOKEMON_DISABLE_INDEX=1`: bypass the Codex index and replay raw logs directly

## Output

CSV output is intended for shell pipelines and spreadsheets.
JSON output includes metadata (`provider`, `range`, `sum_by`, `group_by`) plus aggregated rows.

## Column descriptions

Each output row (CSV row or JSON `rows[]` item) includes:

- `bucket`: bucket start timestamp in local timezone
- `input_tokens`: aggregated input tokens for the bucket/group
- `cached_input_tokens`: aggregated cached input tokens
- `output_tokens`: aggregated output tokens
- `reasoning_output_tokens`: aggregated reasoning output tokens
- `total_tokens`: aggregated total token count

Optional row columns based on `--group-by`:

- `workspace`: present only when `--group-by workspace`
- `session`: present only when `--group-by session`
- `provider`: present only when `--group-by provider`

Provider note:

- For Codex logs, `total_tokens` is based on provider-reported totals where cached/reasoning are subsets of input/output.
- For Claude logs, `total_tokens` is computed as `input_tokens + cached_input_tokens + output_tokens + reasoning_output_tokens`.
