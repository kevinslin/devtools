# arbor usage

`arbor` is a git hygiene helper for cleaning up, deleting, and re-homing linked worktrees.

## Commands

```bash
arbor clean [--base BRANCH] [--dry-run] [--force]
arbor delete <target> [--force]
arbor checkout [worktree]
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

## What `delete` does

1. Resolves `<target>` as either:
- A local branch name.
- A linked worktree path.
- A unique linked worktree directory name.
2. If the target is a branch and that branch is checked out in a linked worktree,
   removes the linked worktree first.
3. Force-deletes the local branch.

When `--force` (or `-f`) is passed, `delete` force-removes dirty worktrees before
deleting the branch.

## What `checkout` does

1. Resolves `[worktree]` as a linked worktree path or unique directory name.
   When omitted, `checkout` uses the current worktree if you run it inside one.
2. Reads the branch currently checked out in that worktree.
3. Refuses to proceed if either the worktree checkout or the main repo checkout
   has uncommitted changes.
4. Detaches the worktree, switches the main repo checkout onto that branch, and
   removes the old linked worktree checkout.

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

# delete a local branch, also removing its linked worktree if present
arbor delete feature/my-branch

# remove a linked worktree by path or unique directory name
arbor delete ../wt-feature-my-branch
arbor delete wt-feature-my-branch

# force-remove a dirty worktree while deleting its branch
arbor delete feature/my-branch --force

# move a linked worktree branch back into the main repo checkout
arbor checkout ../wt-feature-my-branch

# run from inside a linked worktree and convert the current checkout
arbor checkout
```

## Exit codes

- `0`: cleanup completed successfully (including no-op when nothing is merged)
- `1`: one or more worktrees/branches failed to remove
