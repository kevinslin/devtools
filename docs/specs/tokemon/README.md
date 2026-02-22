# Tokemon

Tokemon is a local CLI for reporting token usage from Codex and Claude session logs.

## Quickstart

```sh
# default: current_week, hourly buckets, csv, provider=codex
tokemon
```

## Command

```sh
tokemon [range] [--sum-by N|daily|weekly|monthly] [--group-by none|workspace|provider] [--format csv|json] [--provider codex|claude|all]
```

## Arguments

- `range`:
  - Presets:
    - `current_week`: current Sunday-start week window
    - `week`: trailing 7 days relative to now
    - `month`: trailing 1 calendar month relative to now
    - `year`: last calendar year (`Jan 1` previous year to `Jan 1` current year)
  - Explicit date range: `YYYY-MM-DD YYYY-MM-DD` (inclusive end date)

## Options

- `--sum-by`: bucket size by minutes (for example `15`, `60`) or presets `daily|weekly|monthly` (default: `60`)
- `--group-by`: `none|workspace|provider` (default: `none`)
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

# explicit date range, 30-minute buckets, json output
tokemon 2026-02-01 2026-02-15 --sum-by 30 --format json --provider all
```

## Data sources

- Codex:
  - `~/.codex/sessions/**/*.jsonl`
  - `~/.codex/archived_sessions/*.jsonl`
- Claude:
  - `~/.claude/projects/**/*.jsonl`

## Environment overrides

- `TOKEMON_CODEX_SESSIONS_ROOT`
- `TOKEMON_CODEX_ARCHIVED_ROOT`
- `TOKEMON_CLAUDE_PROJECTS_ROOT`

## Output

CSV output is intended for shell pipelines and spreadsheets.
JSON output includes metadata (`provider`, `range`, `sum_by`, `group_by`) plus aggregated rows.
