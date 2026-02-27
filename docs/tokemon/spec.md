# Tokemon Spec

This document consolidates the prior Tokemon design and architecture docs.

## Design


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

## Architecture


## Document Control
- Status: Implemented (V1)
- Date: 2026-02-22
- Owner: CLI tooling
- Primary code path: `bin/tokemon`

## Scope
This document describes the runtime architecture for `tokemon` as implemented in V1.  
It focuses on component boundaries, data flow, invariants, and extension seams for future subcommands/providers.

## Architectural Principles
1. Local-only processing: read local logs, no network dependencies.
2. Provider-agnostic core: normalize provider-specific events into one record model.
3. Deterministic output: stable sort order and fixed column/field order.
4. Safe degradation: malformed/unreadable lines are skipped without crashing report generation.
5. Extensibility-first command surface: `argparse` subparsers allow new subcommands.

## System Context
Inputs:
1. Codex session JSONL files (`~/.codex/sessions`, `~/.codex/archived_sessions`).
2. Claude project JSONL files (`~/.claude/projects`).
3. CLI flags (`range`, `--sum-by`, `--group-by`, `--format`, `--provider` where provider supports `codex|claude|all`).

Outputs:
1. CSV report to stdout.
2. JSON report to stdout.
3. Validation/runtime errors to stderr with exit code `2`.

## Component Model
### 1. CLI layer
Responsibilities:
1. Parse command and options.
2. Validate static option domains.
3. Execute reporting flow directly from `tokemon`.

Key functions:
1. `_build_parser`
2. `main`

### 2. Range resolution layer
Responsibilities:
1. Resolve presets (`current_week`, `week`, `month`, `year`) in local timezone.
2. Parse explicit date ranges and produce exclusive end bound.
3. Return `(start, end, range_name)` for downstream filtering.

Key function:
1. `_resolve_range`

### 3. Provider discovery layer
Responsibilities:
1. Select default log roots per provider.
2. Accept environment overrides for testability and local customization.
3. Produce a deterministic ordered list of JSONL files.

Key functions:
1. `_codex_files`
2. `_claude_files`

### 4. Provider adapter layer
Responsibilities:
1. Parse provider-native JSONL events.
2. Normalize to `UsageRecord`.
3. Apply provider-specific dedupe/delta logic.
4. Apply range filtering on normalized timestamps.
5. Merge multiple provider streams when `--provider all`.

Key functions:
1. `_iter_codex_usage`
2. `_iter_claude_usage`

Provider-specific invariants:
1. Codex: cumulative `total_token_usage` is converted to per-event delta.
2. Claude: duplicate `(sessionId, message.id)` rows are merged by field-wise max usage.

### 5. Normalization and safety layer
Responsibilities:
1. Parse timestamps robustly with timezone normalization.
2. Coerce token fields to non-negative integers.
3. Reject unusable rows (`None` timestamp, malformed payloads, zeroed records).

Key functions:
1. `_parse_timestamp`
2. `_safe_int`
3. `_normalize_codex_totals`
4. `_normalize_claude_usage`
5. `_is_nonzero`

### 6. Aggregation engine
Responsibilities:
1. Compute bucket boundaries from `--sum-by`.
2. Build composite keys `(bucket, group)` where group is optionally workspace or provider.
3. Sum metrics in fixed token-field order.
4. Produce sorted row output.

Key functions:
1. `_bucket_start`
2. `_aggregate_rows`

### 7. Rendering layer
Responsibilities:
1. Serialize aggregated rows to CSV with fixed headers.
2. Serialize aggregated rows to JSON envelope with metadata.

Key functions:
1. `_write_csv`
2. `_write_json`

## Runtime Data Flow
1. User invokes `tokemon ...`.
2. CLI parser validates option values and command.
3. Range layer resolves `(start, end)` boundaries in local timezone.
4. Selected provider adapter scans files and emits normalized `UsageRecord` stream.
5. Aggregation engine buckets and groups records.
6. Renderer writes CSV or JSON to stdout.
7. Process exits `0` on success, `2` on argument/range validation errors.

## Core Data Contracts
### `UsageRecord`
1. `timestamp`: timezone-aware local `datetime`.
2. `workspace`: string, fallback `(unknown)`.
3. `metrics`:
   - `input_tokens`
   - `cached_input_tokens`
   - `output_tokens`
   - `reasoning_output_tokens`
   - `total_tokens`

### Aggregated row
1. `bucket` (ISO timestamp with minute precision).
2. Optional `workspace`.
3. Same fixed metric fields as `UsageRecord.metrics`.

## Temporal and Boundary Guarantees
1. Range filtering is `[start, end_exclusive)`.
2. Explicit `YYYY-MM-DD YYYY-MM-DD` input is interpreted as inclusive end date, then converted to exclusive bound internally.
3. Bucketing is epoch-based floor by `sum_by_minutes`.
4. All reported buckets are in local timezone.

## Failure Model
Fail-fast:
1. Invalid `--sum-by` (`<= 0`).
2. Invalid range format or unsupported preset.

Best-effort skip:
1. Malformed JSON lines.
2. Missing expected payload sections.
3. Unreadable files.

Rationale:
1. Keep reports available even when a subset of logs is corrupted.
2. Preserve strictness only for user-provided CLI input.

## Complexity and Performance
Let:
1. `F` = number of files scanned.
2. `E` = number of parseable events.
3. `K` = number of output `(bucket,group)` keys.

Complexity:
1. Scan/parse: `O(F + E)`.
2. Aggregation: `O(E)`.
3. Final sort: `O(K log K)`.

Memory:
1. Codex path: bounded by aggregated map plus small per-file state.
2. Claude path: includes dedupe map keyed by `(sessionId,message.id)` before aggregation.

## Extension Architecture
### Add subcommand
1. Introduce subparser registry under `subparsers`.
2. Implement command-specific execution function.
3. Keep adapter/aggregation/rendering primitives reusable.

### Add provider
1. Add file discovery function.
2. Add `iter_<provider>_usage(start, end)` adapter returning `UsageRecord`.
3. Plug adapter selection into `_run_report`.

### Add grouping dimension
1. Extend `--group-by` choices.
2. Add group-key derivation and output column handling.

## Testing Architecture
Current tests (`tests/test_tokemon.py`) validate architecture-critical behavior:
1. Codex cumulative-to-delta correctness.
2. Claude duplicate message merge semantics.
3. Aggregation by bucket/workspace.
4. Invalid input handling and non-zero exit path.

## Architecture Risks
1. Provider log schema drift may break adapter assumptions.
2. Very large historical datasets may create high scan latency without indexing.
3. Deduping by max usage may need revision if provider semantics change.

## Manual Notes 

[keep this for the user to add notes. do not change between edits]

## Changelog
- 2026-02-22: Initial architecture doc for tokemon V1 (`019c868e-b844-76c0-98b5-a12dab1b35ed`)
