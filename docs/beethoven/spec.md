# Beethoven Design

## Document Control
- Status: Draft (Stage 2 refined)
- Date: 2026-02-17
- Design title: `beethoven`
- Goal: Build a tool that transcribes audio with OpenAI APIs and supports question answering over the transcript.

## Problem and Context
The repository currently contains a small utility script (`/Users/kevinlin/code/tools/bin/json_lint.py`) and no existing audio or OpenAI integration flow. We need a focused tool that:
1. Accepts an audio file.
2. Produces a transcript.
3. Persists transcript state so the user can ask follow-up questions later.

## Goals
1. Transcribe common audio formats (`.mp3`, `.wav`, `.m4a`, `.mp4`) via OpenAI APIs.
2. Persist transcript + metadata as a reusable session.
3. Support repeated Q&A over the transcript with citations to transcript segments.
4. Keep the first version CLI-first and scriptable.
5. Minimize moving parts so this can be maintained in this small tools repo.

## Non-Goals
1. Real-time streaming transcription in V1.
2. Speaker diarization guarantees in V1.
3. Multi-user auth or hosted backend.
4. GUI/web app in V1.

## Proposed User Experience
### Commands
1. `beethoven transcribe <audio_path> [--session <name>]`
2. `beethoven ask <session_id_or_name> "<question>"`
3. `beethoven show <session_id_or_name>`

### Expected Flow
1. User runs `transcribe`.
2. Tool uploads audio to OpenAI transcription API and stores normalized transcript chunks.
3. Tool prints session id.
4. User runs `ask` repeatedly; tool retrieves relevant chunks and calls an OpenAI text model for answers.
5. Answer includes citations (chunk indices and timestamps when available).

## Architecture
### A. CLI Layer
- Single executable script in `/Users/kevinlin/code/tools/bin/beethoven.py` (or equivalent wrapper).
- Responsible for argument parsing, user-facing output, and exit codes.

### B. OpenAI Client Layer
- Thin wrapper around:
  - transcription endpoint (audio -> transcript chunks)
  - response/chat endpoint (question + retrieved context -> answer)
- Retry policy: bounded exponential backoff on transient network/rate limit failures.

### C. Session Store
- Local storage under `/Users/kevinlin/code/tools/.beethoven/sessions/<session_id>/`.
- Files:
  - `session.json` (manifest)
  - `transcript.jsonl` (chunked transcript rows)
  - `index.json` (retrieval index metadata/version)

### D. Retrieval + QA
- V1 retrieval: chunk transcript by token/char window and rank via embeddings similarity.
- Fallback path: if transcript is small, pass full transcript directly.
- QA prompt includes:
  - user question
  - top-k chunks
  - citation instruction (always cite chunk ids)

## Control and Config Model
### Environment Variables
1. `OPENAI_API_KEY` (required)
2. `OPENAI_BASE_URL` (optional)
3. `BEETHOVEN_TRANSCRIBE_MODEL` (optional, sensible default)
4. `BEETHOVEN_QA_MODEL` (optional, sensible default)
5. `BEETHOVEN_HOME` (optional override of `.beethoven` storage root)

### Config File (Optional)
- `~/.config/beethoven/config.toml` for default models and retrieval params.
- CLI flags override config file; config file overrides hardcoded defaults.

## Data Model
### `session.json`
- `session_id`
- `created_at`
- `audio_path`
- `audio_sha256`
- `transcribe_model`
- `qa_model`
- `language` (if detected/provided)
- `chunk_count`

### `transcript.jsonl` row
- `chunk_id`
- `start_ms` (nullable)
- `end_ms` (nullable)
- `text`
- `token_count_estimate`
- `embedding` (optional persisted vector ref, depending on implementation)

## Critical Lifecycle Assumptions (Init -> Snapshot -> Consume)
| Value | Source of truth | Init point | Snapshot point | First consumer | Current status |
|---|---|---|---|---|---|
| `session_id` | `session.json` | end of `transcribe` setup | manifest write | `ask` command loader | defined |
| `transcript_chunks` | `transcript.jsonl` | transcription response parse | JSONL flush complete | retrieval ranker | defined |
| `retrieval_index_version` | `index.json` | embedding/index build | index write | QA context builder | defined |
| `qa_context` | in-memory request payload | after retrieval top-k selection | request object assembly | OpenAI QA call | defined |

Boundary note: `ask` must fail fast if snapshot artifacts (`session.json`, `transcript.jsonl`) are incomplete.

## Rollout Plan and Verification Signals
### Rollout
1. Local-only alpha in this repo.
2. Dogfood on 3-5 internal audio files of different lengths.
3. Iterate on chunking/retrieval before broader use.

### Verification Signals
1. Transcription success rate (target: >95% on valid files).
2. `ask` p95 latency under agreed local threshold.
3. Citation coverage (answers include at least one chunk citation).
4. Regression tests pass for parsing/storage/retrieval paths.

## Milestone Breakdown
1. Milestone 1: CLI + transcription + persistent session artifacts.
2. Milestone 2: Basic `ask` over full transcript for short files.
3. Milestone 3: Retrieval index for long transcripts + citation formatting.
4. Milestone 4: Hardening (retry logic, edge-case handling, tests, packaging).

## Risks and Open Questions
1. Model/API churn risk: model names and response formats may evolve; wrappers must isolate schema drift.
2. Large transcript cost/latency: naive full-context prompting will not scale.
3. Timestamp quality: not all transcription outputs guarantee precise timings.
4. Storage growth: embedding persistence may inflate local disk usage.
5. Open question: should V1 include redaction of PII before transcript persistence?

## Stage 2 Review Findings (Resolved)
### Blocker
1. Missing persistence contract for cross-command usage.
   - Resolution: added explicit on-disk artifact schema and fail-fast boundary rules.

### Major
1. Ambiguous retrieval strategy for long transcripts.
   - Resolution: defined embedding-based ranking with small-transcript fallback.
2. Unclear configuration precedence.
   - Resolution: defined CLI > config file > defaults precedence.

### Minor
1. Verification criteria were too vague.
   - Resolution: added concrete verification signals for success rate, latency, and citations.

## Evidence Used in Refinement
1. Repository scan shows no existing audio/transcript subsystem, so design assumes greenfield implementation in this repo.
2. Existing script at `/Users/kevinlin/code/tools/bin/json_lint.py` suggests lightweight CLI utility style is appropriate.

## Stage Gate
Planloop Stage 2 is complete. Stop here for user input before Stage 3 (`spec-{num}-{milestone}.md`) generation.
