# arbor usage

`arbor` is a git hygiene helper for cleaning local branches and linked worktrees.

## Command

```bash
arbor clean [--base BRANCH] [--dry-run] [--force]
```

## What `clean` does

1. Determines a merge base reference:
- Uses `--base` when provided.
- Otherwise uses `origin/HEAD` when available.
- Falls back to the current branch.
2. Finds local branches fully merged into that base.
3. Removes linked worktrees whose branch is fully merged.
4. Deletes merged local branches that are not active in any worktree.

`clean` never deletes the base branch and never deletes the current branch.

When `--dry-run` (or `-n`) is passed, `arbor` prints what it would remove/delete
without making any repository changes.

When `--force` (or `-f`) is passed, `arbor` force-removes merged worktrees,
including worktrees with modified files.

## Examples

```bash
# clean against default base (origin/HEAD or current branch)
arbor clean

# clean against a specific base branch
arbor clean --base main

# preview cleanup without changing anything
arbor clean --base main --dry-run

# force cleanup of merged worktrees even if they are dirty
arbor clean --base main --force
```

## Exit codes

- `0`: cleanup completed successfully (including no-op when nothing is merged)
- `1`: one or more worktrees/branches failed to remove
