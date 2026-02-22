# Tokemon Design

## Document Control
- Status: Implemented (V1)
- Date: 2026-02-22
- Design title: `tokemon`
- Goal: Provide a local CLI that reports token usage from Codex and Claude session logs with consistent aggregation and export formats.

## Problem and Context
`tokemon` exists to answer: "How many tokens did I use over a time range?" across two providers with different local log schemas.  
The design prioritizes:
1. Local-first operation with no network calls.
2. Stable output for shell pipelines and spreadsheet workflows.
3. Extensibility for additional providers and future subcommands.

## Goals
1. Support one command surface: `tokemon`.
2. Support range presets and explicit date ranges.
3. Support configurable time bucketing (`--sum-by`).
4. Support optional grouping by workspace or provider (`--group-by workspace|provider`).
5. Support CSV and JSON output (`--format`).
6. Support provider modes `codex`, `claude`, and `all` (`codex+claude`).

## Non-Goals
1. Cost estimation in USD.
2. Live/streaming token telemetry.
3. Provider API calls or cloud synchronization.
4. Multi-command analytics suite in V1.

## Command Contract
```sh
tokemon [range] [--sum-by N] [--group-by none|workspace|provider] [--format csv|json] [--provider codex|claude|all]
```

### Range semantics
1. Default: `current_week`.
2. Presets:
   - `current_week`: Sunday 00:00 local time through next Sunday 00:00 (exclusive).
   - `week`: trailing 7-day window relative to now.
   - `month`: trailing 1-calendar-month window relative to now.
   - `year`: trailing 12-calendar-month window relative to now.
3. Explicit range: `YYYY-MM-DD YYYY-MM-DD` with inclusive end date.
   - Internally converted to `[start@00:00, (end+1 day)@00:00)` for exclusive upper bound filtering.

## High-Level Architecture
`bin/tokemon` is a single-file Python CLI organized in five layers:
1. CLI parsing layer (`argparse`) for direct invocation.
2. Provider file discovery layer (Codex and Claude roots).
3. Provider event extraction and normalization layer.
4. Aggregation layer (time buckets + optional group keys).
5. Rendering layer (CSV or JSON).

## Data Sources
### Codex provider
- Default roots:
  - `~/.codex/sessions/**/*.jsonl`
  - `~/.codex/archived_sessions/*.jsonl`
- Override env vars:
  - `TOKEMON_CODEX_SESSIONS_ROOT`
  - `TOKEMON_CODEX_ARCHIVED_ROOT`

### Claude provider
- Default root:
  - `~/.claude/projects/**/*.jsonl`
- Override env var:
  - `TOKEMON_CLAUDE_PROJECTS_ROOT`

### All provider mode
- `--provider all` reads both codex and claude sources and aggregates them together.

## Provider Adapter Design
### Codex adapter
`event_msg` rows contain cumulative `total_token_usage`.  
Design decision: convert cumulative totals to per-event deltas.

Algorithm:
1. Track `previous_totals` per file.
2. For each token_count event:
   - Parse current totals.
   - Compute `delta = current - previous`.
   - If delta is negative (counter reset), fall back to current value.
3. Drop zero-delta records.
4. Attach workspace from latest `session_meta.payload.cwd`; fallback `(unknown)`.

Rationale:
- Avoid double counting repeated cumulative snapshots.
- Preserve correctness when sessions reset/restart.

### Claude adapter
Claude logs may emit multiple entries for the same assistant message ID.  
Design decision: dedupe by `(sessionId, message.id)` and keep maximum usage per field.

Algorithm:
1. Read assistant entries only.
2. Normalize usage:
   - `input_tokens`
   - `cached_input_tokens = cache_creation_input_tokens + cache_read_input_tokens`
   - `output_tokens`
   - `reasoning_output_tokens` (if present)
   - `total_tokens = sum(all normalized fields)`
3. Merge duplicate message keys by field-wise max.
4. Keep latest timestamp and best available workspace.

Rationale:
- Prevent double counting message revisions/tool-use expansions.
- Preserve final observed usage for each message.

## Normalized Record Model
Intermediate records use:
- `timestamp` (local timezone-aware datetime)
- `workspace` (string; fallback `(unknown)`)
- `metrics`:
  - `input_tokens`
  - `cached_input_tokens`
  - `output_tokens`
  - `reasoning_output_tokens`
  - `total_tokens`

## Aggregation Model
1. Bucket key:
   - `bucket = floor(timestamp_epoch / (sum_by_minutes * 60))`.
2. Group key:
   - none: `""`
   - workspace: normalized workspace string.
   - provider: provider label (`codex` or `claude`).
3. Aggregate by summing each metric per `(bucket, group)` pair.
4. Sort output by `(bucket, group)` ascending.

## Output Contract
### CSV (`--format csv`, default)
Columns:
1. `bucket`
2. `workspace` (only when `--group-by workspace`)
3. `provider` (only when `--group-by provider`)
4. token fields in fixed order

### JSON (`--format json`)
Envelope:
1. `provider`
2. `range`
3. `start`
4. `end_exclusive`
5. `sum_by`
6. `sum_by_minutes`
7. `group_by`
8. `rows` (aggregated rows)

## Error Handling and Exit Codes
1. Invalid `--sum-by` (`<=0`) -> stderr error, exit `2`.
2. Invalid range preset/date shape/order -> stderr error, exit `2`.
3. Unreadable files or malformed JSON lines are skipped best-effort.
4. Empty result sets still return valid CSV/JSON with no data rows.

## Time and Locale Semantics
1. All internal timestamp comparisons are done in local timezone.
2. Input timestamps with `Z` are converted from UTC to local time.
3. Date presets and date-range boundaries are evaluated in local timezone.

## Critical Lifecycle Assumptions (Init -> Snapshot -> Consume)
| Value | Source of truth | Init point | Snapshot point | First consumer | Current status |
|---|---|---|---|---|---|
| `provider` | CLI args | argparse parse | `_run_report` | adapter selection | implemented |
| `start,end` | range parser | `_resolve_range` | return tuple | record filtering | implemented |
| `workspace` | provider logs | per parsed event | `UsageRecord` creation | group key derivation | implemented |
| `metrics` | provider usage payload | adapter normalization | `UsageRecord` creation | bucket aggregation | implemented |
| `rows` | aggregation map | first accepted record | emit-time row materialization | CSV/JSON writers | implemented |

## Verification Strategy
Implemented tests in `tests/test_tokemon.py` cover:
1. Codex cumulative-total-to-delta conversion.
2. Workspace grouping in CSV output.
3. Claude message deduplication by `(sessionId, message.id)`.
4. Invalid range error handling.

Manual checks validate:
1. Help output and option parsing.
2. Real local log scans for both providers.

## Extensibility Plan
1. Add new subcommands by introducing `argparse` subparsers when command surface expands.
2. Add providers by implementing a new `iter_<provider>_usage(start, end)` adapter returning normalized `UsageRecord`.
3. Add group dimensions by extending group-key derivation and row schema.
4. Add optional cost reporting by introducing a post-aggregation pricing mapper (kept out of V1 core path).

## Risks and Open Questions
1. Provider log schema drift may require adapter updates.
2. Very large history directories can increase scan time; no index/cache exists in V1.
3. Claude cache token semantics may evolve; current normalization reflects known fields.
4. Future question: should date presets include "rolling last 7 days" separate from calendar week semantics?

## Manual Notes 

[keep this for the user to add notes. do not change between edits]

## Changelog
- 2026-02-22: Initial tokemon design doc for implemented V1 CLI (`019c868e-b844-76c0-98b5-a12dab1b35ed`)
