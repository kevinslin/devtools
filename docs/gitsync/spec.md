# Feature Spec: Per-repository sync modes

**Date:** 2026-08-06
**Status:** Approved
**Owner:** `gitsync` CLI

## Problem and Decision

`gitsync` currently fetches and merges remote commits, then pushes the resulting
local branch for every configured repository. Some repositories must consume
remote changes without ever publishing local commits.

Add a per-repository `mode` field with two values:

- `push/pull`: fetch and merge the configured upstream, then push the resulting
  branch. This preserves the current behavior.
- `pull`: fetch and merge the configured upstream, but never invoke `git push`.

When `mode` is omitted, it defaults to `push/pull` for compatibility with
existing configuration. Mode is owned by `~/.config/gitsync/agcron.json`; CLI
selectors do not override it.

## Scope

**Changes**

- Extend each repository configuration with the optional `mode` field.
- Make remote validation and the final push step mode-aware.
- Report the selected mode and an explicit skipped-push result in JSON output.
- Add integration coverage for pull-only success, dirty-worktree denial, and
  conflict recovery.
- Update [usage.md](usage.md) with the mode contract and examples.

**Does not change**

- Cron matching, launchd registration, due-claim state, or repository locks.
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
      "path": "/Users/kevinlin/agents",
      "repo": "https://github.com/openai/kevinlin-agents.git",
      "sync_schedule": "*/10 * * * *",
      "mode": "pull"
    }
  ]
}
```

`mode` must be `push/pull` or `pull`. Any other value is a configuration error
and exits with code `2`. An omitted field is interpreted as `push/pull`.

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
   [bin/gitsync](../../bin/gitsync) to accept optional `mode`, default it to
   `push/pull`, and reject unsupported values.
2. Split repository validation into shared fetch validation and
   `push/pull`-only push-URL validation.
3. Keep the shared fetch, comparison, merge, and Codex conflict path, but make
   the resolver prompt mode-aware: in `pull`, explicitly prohibit pushes and
   all remote mutation, and run it with push-blocking Git guards. Branch before
   `_push` and emit `push: "skipped"` for `pull`.
4. Add `mode` to success and blocked result objects so every selected entry is
   attributable to its configured behavior.
5. Expand [tests/test_gitsync.py](../../tests/test_gitsync.py) and update
   [usage.md](usage.md). After approval, add an explicit mode to the live config
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
| Existing push/pull behavior does not regress | Run the full focused `test_gitsync.py` suite, including push retry, upstream targeting, locks, cron, and manual `--force`. |

## Approved Decisions

- Omitted `mode` defaults to `push/pull` rather than becoming immediately
  mandatory, avoiding a breaking configuration migration.
- Pull-only mode ignores the push URL and validates only the fetch identity,
  because it cannot exercise push capability.

## Manual Notes

[keep this for the user to add notes. do not change between edits]

## Changelog
- 2026-08-06 09:56: Proposed per-repository `push/pull` and `pull` modes for review; no implementation changes applied. (019fd480-9f24-7742-bce7-c362e6bc5261 - 2d3f9d8c429ee1871ef186fbb4774c8692a5cdcd)
- 2026-08-06: Approved the proposed mode contract for implementation. (019fd480-9f24-7742-bce7-c362e6bc5261)
- 2026-08-06: Implemented mode-aware sync, guarded pull-only conflict resolution, documentation, and focused integration coverage. (019fd480-9f24-7742-bce7-c362e6bc5261)
