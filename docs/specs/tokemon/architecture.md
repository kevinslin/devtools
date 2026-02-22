# Tokemon Architecture

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
2. Build composite keys `(bucket, group)` where group is optionally workspace.
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
