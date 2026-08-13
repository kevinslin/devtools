# Feature Spec: Per-repository sync modes and post-sync hooks

**Date:** 2026-08-06; updated 2026-08-09
**Status:** Approved
**Owner:** `gitsync` CLI

## Problem and Decision

Some repositories must consume remote changes without publishing local commits.
Others need trusted repository-specific automation after synchronization, such
as applying newly pulled chezmoi configuration while preserving local edits.

Add a per-repository `mode` field with two values:

- `push/pull`: fetch and merge the configured upstream, then push the resulting
  branch. This preserves the current behavior.
- `pull`: fetch and merge the configured upstream, but never invoke `git push`.

When `mode` is omitted, it defaults to `push/pull` for compatibility with
existing configuration. Mode is owned by `~/.config/gitsync/agcron.json`; CLI
selectors do not override it.

Extend the existing optional per-repository `post_sync` field to accept either
one argument array or an ordered, non-empty array of argument arrays. Preserve
existing single-hook configurations unchanged, and run multi-hook
configurations in their configured order. Execute every hook directly, without
a shell, after every successful Git synchronization, including no-op syncs and
newly cloned repositories.

## Scope

**Changes**

- Extend each repository configuration with optional `mode` and `post_sync`
  fields; support ordered hook lists without changing existing single-hook
  behavior.
- Make remote validation and the final push step mode-aware.
- Report the selected mode and an explicit skipped-push result in JSON output.
- Execute trusted post-sync hooks in order inside the repository lock with
  repository identity and old/new Git heads exposed through environment
  variables, stopping at the first failure.
- Release a scheduled due claim only when one of its post-sync hooks fails,
  allowing a same-minute retry without changing ordinary blocker suppression.
- Add a read-only `status` command exposing configured repositories, their
  latest successful fetch timestamps, and their current dirty-worktree state.
- Store fetch history, schedule claims, and repository locks in
  `$XDG_STATE_HOME/gitsync/`, defaulting to `~/.local/state/gitsync/`, while
  preserving the existing `GITSYNC_STATE_DIR` override.
- Append a private, structured record for every sync run to the local-date
  file `/tmp/gitsync-YYYY-MM-DD.log`.
- Add integration coverage for pull-only success, dirty-worktree denial, and
  conflict recovery, hook validation and execution, guarded ordinary pushes,
  and scheduled retry behavior.
- Update [README.md](../README.md) with the mode contract, hook behavior, and the
  `kevinlin-agents` chezmoi reconciliation example.

**Does not change**

- Cron matching, launchd registration, repository locks, or due-claim behavior
  for ordinary repository blockers.
- The meaning of `sync --force`: it bypasses schedules but never overrides mode
  or enables Git force-push.
- Detached-HEAD, missing-upstream, repository identity, authentication, and
  non-fast-forward safety behavior except where explicitly mode-dependent.
- The prohibition on reset, discard, force-push, or auto-committing ordinary
  user changes.

## Contract

### Configuration

```json
{
  "repos": [
    {
      "name": "agents",
      "path": "~/agents",
      "repo": "https://github.com/openai/kevinlin-agents.git",
      "sync_schedule": "*/10 * * * *",
      "mode": "pull",
      "post_sync": [
        ["~/code/devtools/tools/gitsync/scripts/chezmoi-post-sync"],
        ["~/code/devtools/tools/gitsync/scripts/launchd-sync"]
      ]
    }
  ]
}
```

`mode` must be `push/pull` or `pull`. Any other value is a configuration error
and exits with code `2`. An omitted field is interpreted as `push/pull`.

`path` must resolve to an absolute path after expanding a leading `~`.
`post_sync`, when present, accepts either one non-empty array of non-empty
string arguments, such as `["script", "--arg"]`, or a non-empty ordered array
of argument arrays, such as `[["first"], ["second", "--arg"]]`. Every nested
argument array must be non-empty and contain only non-empty strings. Mixed
single-command and multi-command shapes are invalid. Existing single-hook
configurations remain valid unchanged, and omitting `post_sync` remains valid.
Invalid hooks fail configuration validation with exit code `2` before any Git
operation.

| Mode | Fetch and merge | Push | Remote identities checked |
| --- | --- | --- | --- |
| `push/pull` | Yes | Yes | `origin` fetch and push URLs |
| `pull` | Yes | Never | `origin` fetch URL only |

The fetch URL must identify the configured `repo` in both modes. A pull-only
repository does not use its push URL, so a distinct or missing push URL does not
block the run.

### Safety and execution order

For each selected repository, [bin/gitsync](../bin/gitsync) must:

1. Acquire the existing canonical-path repository lock.
2. Clone a missing repository from `repo`, or verify the existing path is a Git
   worktree.
3. Require an attached branch and configured `origin` upstream.
4. Run `git status --porcelain` and block before fetch when any staged,
   unstaged, or untracked change exists.
5. Validate the mode-required remote identities.
6. Fetch `origin`, compare `HEAD...@{upstream}`, and merge incoming commits.
7. Invoke the existing narrowly scoped `codex exec` conflict resolver when the
   merge produces unmerged paths.
8. Verify that Codex completed the merge, left no unmerged paths, and left a
   clean worktree.
9. Push only in `push/pull` mode.
10. Execute each configured `post_sync` command in order while the repository
    lock remains held. Stop at the first nonzero exit or missing executable and
    treat it as a blocked sync.

The dirty-worktree blocker applies to both modes. In particular, `pull` mode
must not fetch or merge when the worktree is dirty.

Conflict behavior is identical in both modes. If local and remote committed
histories conflict, Codex may complete the merge commit locally. In `pull`
mode, the resolver prompt must explicitly forbid `git push` and every other
remote mutation. Codex must run in its workspace-write sandbox, and its
execution environment must also block Git push/send-pack operations and inject
a failing pre-push hook; the merge commit remains local. If Codex cannot resolve
the conflict safely, `gitsync` preserves the in-progress conflict and returns
the existing exact blocker.

### Post-sync execution and retries

Hooks run with the repository as their current working directory and receive:

- `GITSYNC_REPO_PATH`: canonical absolute repository path.
- `GITSYNC_REPO_NAME`: configured repository name.
- `GITSYNC_OLD_HEAD`: checked-out commit before fetching and merging.
- `GITSYNC_NEW_HEAD`: checked-out commit after synchronization.

A freshly cloned repository uses its initial checked-out commit as
`GITSYNC_OLD_HEAD`; old and new heads are normally equal. Every hook receives
the same repository context and old/new heads. A leading `~` is expanded only
in each hook's executable path (`argv[0]`). Hook arguments are passed directly
to `subprocess.run` with `shell=False`, so shell metacharacters, argument-level
`~`, and environment variables remain literal.

In pull-only mode, every hook inherits the existing Git wrapper and failing
pre-push hook. These prevent ordinary accidental Git pushes but are not a
security boundary for malicious code. Configure only trusted hooks.

A missing or failing hook immediately stops the sequence, so subsequent hooks
do not run. It raises a distinct post-sync error, preserves the already
synchronized Git worktree, and returns a blocked repository result. For
`sync --due`, only this error releases the repository's current-minute claim;
dirty-worktree, authentication, identity, and merge blockers retain their
existing claim. A same-minute retry starts a new synchronization and reruns the
hook sequence from its first configured entry; earlier successful hooks can
therefore run again. Other repositories' scheduled claims are unchanged.

### Agents repository reconciliation

`kevinlin-agents` configures the devtools-owned
`~/code/devtools/tools/gitsync/scripts/chezmoi-post-sync` and
`~/code/devtools/tools/gitsync/scripts/launchd-sync` executables, in that order.
Its `agcron.json` template preserves their portable home-relative paths. The
devtools repository owns both hooks and supplies the generic execution
contract; pull-only synchronization applies the same Git push guard to each.

The hook renders the previous and current standalone chezmoi sources, compares
them with each local destination, and applies incoming-only changes without
discarding local-only edits. Divergent changes are backed up under
`~/.local/state/kevinlin-agents/chezmoi-post-sync/backups/` before attempting a
three-way merge. Unresolved conflicts preserve the destination, retain their
original merge baseline across retries and later upstream commits, and send a
deduplicated Slack notification through `slack-notify`.

Private target modes are preserved; destination symlinks are backed up without
dereferencing them, directories are never recursively copied, and removed
managed entries do not delete existing destination files. Repository-local
`config/AGENTS.md` and `config/README.md` are excluded through
`config/.chezmoiignore`.

After chezmoi reconciliation succeeds, `launchd-sync` reconciles owned
LaunchAgents against `~/.config/gitsync/launchd-jobs.json` and the staged plist
files under `~/.config/gitsync/`. The shared policy and staged plists are
chezmoi-managed configuration; the executable remains in devtools. The policy
alone declares each job's ownership and `all_machine` or `primary_only`
placement, without hardcoded label-prefix restrictions.

### Result output

Each repository result adds `mode`. The `push` field remains present so current
JSON consumers retain a stable shape:

```json
{
  "name": "agents",
  "mode": "pull",
  "pulled": true,
  "push": "skipped",
  "status": "ok"
}
```

`push/pull` retains `no-op`, `pushed`, and `pushed-after-retry`. `pull` always
reports `skipped`, including when no incoming commit exists.

### Repository status and persistent state

`gitsync status` loads every configured repository and returns a JSON object
with `status: "ok"` and a `repos` array. Each entry includes the repository
name, canonical path, configured remote, schedule, mode, `last_fetched`,
`dirty`, and per-repository status. Missing checkouts and invalid paths are
reported rather than cloned or repaired. Worktree inspection uses Git's
`--no-optional-locks` mode; status never fetches or writes state.

Every successful `git fetch` immediately records a timezone-aware timestamp in
an atomically replaced, per-repository state file. This timestamp remains
available if a later merge, push, or post-sync hook fails. Repositories with no
recorded gitsync history fall back to the modification time of `FETCH_HEAD`;
repositories without either source report `null`.

Persistent repository history, schedule claims, and locks share the XDG state
root: `$XDG_STATE_HOME/gitsync/`, or `~/.local/state/gitsync/` by default.
`GITSYNC_STATE_DIR` takes precedence when explicitly configured.

### Daily sync-run logging

Each parsed `sync` invocation appends one compact JSON line to
`/tmp/gitsync-YYYY-MM-DD.log`, using the current local date and a
timezone-aware timestamp. Records include the resolved config path, requested
selection, exit code, overall status, and either the repository result summary
or configuration error. Blocked repositories, empty due selections, and
configuration failures are logged without altering existing stdout, stderr,
or exit-code contracts. `status`, `validate`, and `launchd-plist` never create
run logs.

The log is opened with append-only, close-on-exec, no-follow, and nonblocking
flags. The resulting descriptor must identify a regular, single-link file
owned by the current user with mode `0600`; unsafe symlinks, FIFOs, hardlinks,
or permissive files are rejected. Logging errors are reported as warnings but
never turn a completed synchronization into a failure. `GITSYNC_LOG_DIR`
provides an explicit isolated-test override.

## Implementation

1. Extend `RepoConfig` and `load_config` in
   [bin/gitsync](../bin/gitsync) to accept optional `mode` and `post_sync`,
   default the mode to `push/pull`, normalize either supported hook shape into
   an ordered command sequence, and reject unsupported values, invalid argument
   arrays, or invalid hook lists.
2. Split repository validation into shared fetch validation and
   `push/pull`-only push-URL validation.
3. Keep the shared fetch, comparison, merge, and Codex conflict path, but make
   the resolver prompt mode-aware: in `pull`, explicitly prohibit pushes and
   all remote mutation, and run it with push-blocking Git guards. Branch before
   `_push` and emit `push: "skipped"` for `pull`.
4. Add `mode` to success and blocked result objects so every selected entry is
   attributable to its configured behavior.
5. Execute each configured hook in order after Git synchronization, passing
   the repository identity and old/new heads to each while retaining the
   repository lock and pull-mode guard. Stop at the first failure.
6. Release the current-minute due claim only for the repository whose hook
   failed; preserve existing claim behavior for every ordinary repository
   blocker.
7. Expand [tests/test_gitsync.py](../../../tests/test_gitsync.py) and update
   [README.md](../README.md). Activate only the managed gitsync configuration target
   and validate it before the next scheduled run.

## Verification

| Required outcome | How to verify |
| --- | --- |
| Omitted mode preserves existing behavior | Config without `mode` performs fetch, merge, and no-op or real push; output reports `push/pull`. |
| Invalid mode fails before Git mutation | CLI integration test expects exit `2` and a mode validation error. |
| Pull-only mode never pushes | Advance the remote, run `sync`, verify the local HEAD updates and the remote receives no new ref update. |
| Ahead-only pull remains local | Create a local-only commit with no incoming commits, run `sync`, assert `pulled: false`, `push: "skipped"`, and an unchanged remote tip. |
| Dirty pull-only worktree is untouched | Create an untracked or modified file, run `sync`, assert the dirty blocker and unchanged `FETCH_HEAD` and HEAD. |
| Pull-only divergence merges locally | Create non-conflicting local and remote commits, run `sync`, verify both are in local history and the remote tip is unchanged. |
| Pull-only conflicts use the guarded resolver | Create conflicting committed changes, make the fake Codex resolver attempt a push, verify the push is rejected, the local merge is clean, and the remote tip is unchanged. |
| Unsafe conflict resolution remains blocked | Use a failing fake Codex executable and assert the exact conflict blocker and preserved merge state. |
| Push URL validation is mode-aware | Configure a different push URL: `pull` succeeds when fetch identity matches; `push/pull` blocks. |
| Hook configuration fails closed | Reject null, empty, non-array, mixed-shape, empty-hook, or invalid-argument `post_sync` values before mutating Git. Omitting the field remains valid. |
| Single-hook compatibility and ordered execution are preserved | Verify existing flat `post_sync` argument arrays still run unchanged, while nested argument arrays run every configured command in order. |
| Hooks receive the correct context | Run no-op, fast-forward, and newly cloned syncs; assert working directory, literal argv, repository identity, and old/new heads. |
| Pull-only hooks reject ordinary pushes | Execute an ordinary `git push` from a trusted test hook and verify the wrapper blocks it without changing the remote. |
| Hook failures stop execution and retry without broadening retries | Fail an intermediate hook, verify later hooks do not run and only its due claim is released, then verify a retry starts the sequence from its first hook; an ordinary dirty-worktree blocker keeps its claim. |
| Status inventories repositories safely | Configure clean, dirty, and missing repositories; verify all are listed without fetch, clone, or state writes. |
| Successful fetch history remains observable | Verify a timezone-aware timestamp survives successful sync and later hook failure, with `FETCH_HEAD` fallback for older repositories. |
| Persistent state follows XDG conventions | Set `XDG_STATE_HOME` and verify fetch records and repository locks are created under its `gitsync/` subdirectory. |
| Daily run logs capture real outcomes safely | Run successful and blocked syncs; assert appended dated JSON records, timezone-aware timestamps, exit codes, blockers, and mode `0600`. |
| Logging preserves read-only and safety boundaries | Verify non-sync commands do not create logs, configuration failures are recorded, and symlinked log targets are refused without changing sync results. |
| Agents reconciliation works end to end | Pull a temporary upstream commit through real `gitsync`; execute the committed agents hook and verify chezmoi updates the private destination. |
| Conflicting local changes remain recoverable | Verify backups, clean three-way merges, deduplicated Slack escalation, preserved symlinks, and pending baselines across later upstream commits. |
| Existing push/pull behavior does not regress | Run the full focused `test_gitsync.py` suite, including push retry, upstream targeting, locks, cron, and manual `--force`. |

## Approved Decisions

- Omitted `mode` defaults to `push/pull` rather than becoming immediately
  mandatory, avoiding a breaking configuration migration.
- Pull-only mode ignores the push URL and validates only the fetch identity,
  because it cannot exercise push capability.
- Post-sync hooks are trusted executable argument arrays, not shell strings or
  a sandbox for untrusted code.
- The existing `post_sync` field supports its original single-command argument
  array and an ordered, non-empty array of command argument arrays.
- Only post-sync failures release their current-minute schedule claim; ordinary
  sync blockers preserve existing suppression.

## Manual Notes

[keep this for the user to add notes. do not change between edits]

## Changelog
- 2026-08-06 09:56: Proposed per-repository `push/pull` and `pull` modes for review; no implementation changes applied. (019fd480-9f24-7742-bce7-c362e6bc5261 - 2d3f9d8c429ee1871ef186fbb4774c8692a5cdcd)
- 2026-08-06: Approved the proposed mode contract for implementation. (019fd480-9f24-7742-bce7-c362e6bc5261)
- 2026-08-06: Implemented mode-aware sync, guarded pull-only conflict resolution, documentation, and focused integration coverage. (019fd480-9f24-7742-bce7-c362e6bc5261)
- 2026-08-08: Documented optional post-sync hooks, guarded execution and retry semantics, and the agents chezmoi reconciliation workflow.
- 2026-08-09: Moved the chezmoi reconciliation hook into devtools and expanded home-relative hook executable paths without expanding hook arguments.
- 2026-08-09: Documented single-field `post_sync` compatibility, ordered hook lists, fail-fast execution, guarded context, and unchanged retry semantics.
