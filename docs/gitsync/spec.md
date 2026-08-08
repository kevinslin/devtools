# Feature Spec: Per-repository sync modes and post-sync hooks

**Date:** 2026-08-06; updated 2026-08-08
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

Add an optional per-repository `post_sync` argument array. Run it directly,
without a shell, after every successful Git synchronization, including no-op
syncs and newly cloned repositories.

## Scope

**Changes**

- Extend each repository configuration with optional `mode` and `post_sync`
  fields.
- Make remote validation and the final push step mode-aware.
- Report the selected mode and an explicit skipped-push result in JSON output.
- Execute trusted post-sync hooks inside the repository lock with repository
  identity and old/new Git heads exposed through environment variables.
- Release a scheduled due claim only when its post-sync hook fails, allowing a
  same-minute retry without changing ordinary blocker suppression.
- Add integration coverage for pull-only success, dirty-worktree denial, and
  conflict recovery, hook validation and execution, guarded ordinary pushes,
  and scheduled retry behavior.
- Update [usage.md](usage.md) with the mode contract, hook behavior, and the
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
      "post_sync": ["./scripts/chezmoi-post-sync"]
    }
  ]
}
```

`mode` must be `push/pull` or `pull`. Any other value is a configuration error
and exits with code `2`. An omitted field is interpreted as `push/pull`.

`path` must resolve to an absolute path after expanding a leading `~`.
`post_sync`, when present, must be a non-empty array of non-empty string
arguments. Invalid hooks fail configuration validation with exit code `2`
before any Git operation.

| Mode | Fetch and merge | Push | Remote identities checked |
| --- | --- | --- | --- |
| `push/pull` | Yes | Yes | `origin` fetch and push URLs |
| `pull` | Yes | Never | `origin` fetch URL only |

The fetch URL must identify the configured `repo` in both modes. A pull-only
repository does not use its push URL, so a distinct or missing push URL does not
block the run.

### Safety and execution order

For each selected repository, [bin/gitsync](../../bin/gitsync) must:

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
10. Execute the optional `post_sync` hook while the repository lock remains
    held. Treat a nonzero exit or missing executable as a blocked sync.

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
`GITSYNC_OLD_HEAD`; old and new heads are normally equal. Hook arguments are
passed directly to `subprocess.run` with `shell=False`, so shell metacharacters
are literal.

In pull-only mode, hooks inherit the existing Git wrapper and failing pre-push
hook. These prevent ordinary accidental Git pushes but are not a security
boundary for malicious code. Configure only trusted hooks.

A missing or failing hook raises a distinct post-sync error, preserves the
already synchronized Git worktree, and returns a blocked repository result.
For `sync --due`, only this error releases the repository's current-minute
claim; dirty-worktree, authentication, identity, and merge blockers retain
their existing claim. Other repositories' scheduled claims are unchanged.

### Agents repository reconciliation

`kevinlin-agents` configures `./scripts/chezmoi-post-sync`. That repository owns
the hook; `gitsync` only supplies the generic execution contract.

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

## Implementation

1. Extend `RepoConfig` and `load_config` in
   [bin/gitsync](../../bin/gitsync) to accept optional `mode` and `post_sync`,
   default the mode to `push/pull`, and reject unsupported values or invalid
   hook argument arrays.
2. Split repository validation into shared fetch validation and
   `push/pull`-only push-URL validation.
3. Keep the shared fetch, comparison, merge, and Codex conflict path, but make
   the resolver prompt mode-aware: in `pull`, explicitly prohibit pushes and
   all remote mutation, and run it with push-blocking Git guards. Branch before
   `_push` and emit `push: "skipped"` for `pull`.
4. Add `mode` to success and blocked result objects so every selected entry is
   attributable to its configured behavior.
5. Execute the optional post-sync hook after Git synchronization, passing the
   repository identity and old/new heads while retaining the repository lock.
6. Release the current-minute due claim only for the failed hook's repository;
   preserve existing claim behavior for every ordinary repository blocker.
7. Expand [tests/test_gitsync.py](../../tests/test_gitsync.py) and update
   [usage.md](usage.md). Activate only the managed gitsync configuration target
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
| Hook configuration fails closed | Reject null, empty, non-array, or non-string `post_sync` values before mutating Git; an omitted hook remains valid. |
| Hooks receive the correct context | Run no-op, fast-forward, and newly cloned syncs; assert working directory, literal argv, repository identity, and old/new heads. |
| Pull-only hooks reject ordinary pushes | Execute an ordinary `git push` from a trusted test hook and verify the wrapper blocks it without changing the remote. |
| Hook failures retry without broadening retries | Assert a failed post-sync hook releases only its due claim while an ordinary dirty-worktree blocker keeps its claim. |
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
- Only post-sync failures release their current-minute schedule claim; ordinary
  sync blockers preserve existing suppression.

## Manual Notes

[keep this for the user to add notes. do not change between edits]

## Changelog
- 2026-08-06 09:56: Proposed per-repository `push/pull` and `pull` modes for review; no implementation changes applied. (019fd480-9f24-7742-bce7-c362e6bc5261 - 2d3f9d8c429ee1871ef186fbb4774c8692a5cdcd)
- 2026-08-06: Approved the proposed mode contract for implementation. (019fd480-9f24-7742-bce7-c362e6bc5261)
- 2026-08-06: Implemented mode-aware sync, guarded pull-only conflict resolution, documentation, and focused integration coverage. (019fd480-9f24-7742-bce7-c362e6bc5261)
- 2026-08-08: Documented optional post-sync hooks, guarded execution and retry semantics, and the agents chezmoi reconciliation workflow.
