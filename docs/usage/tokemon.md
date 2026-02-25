# Tokemon

Tokemon is a local CLI for reporting token usage from Codex and Claude session logs.

## Quickstart

```sh
# default: current_week, hourly buckets, csv, provider=codex
tokemon
```

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

## Environment overrides

- `TOKEMON_CODEX_SESSIONS_ROOT`
- `TOKEMON_CODEX_ARCHIVED_ROOT`
- `TOKEMON_CLAUDE_PROJECTS_ROOT`

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
