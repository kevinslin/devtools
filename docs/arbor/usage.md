# arbor usage

`arbor` is a git hygiene helper for cleaning up, removing, re-homing, and creating linked worktrees.
It can also force-push the current branch with lease.

## Commands

```bash
arbor clean [--base BRANCH] [--dry-run] [--force]
arbor remove <target> [<target> ...] [--force]
arbor checkout [worktree]
arbor convert-to-worktree [worktree] [--base BRANCH]
arbor push-force
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

When `--dry-run` (or `-n`) is passed, `arbor` prints what it would remove
without making any repository changes.

When `--force` (or `-f`) is passed, `arbor` force-removes merged worktrees,
including worktrees with modified files.

## What `remove` does

1. Resolves each `<target>` as either:
- A local branch name.
- A linked worktree path.
- A unique linked worktree directory name.
2. If a target is a branch and that branch is checked out in a linked worktree,
   removes the linked worktree first.
3. Deletes targeted local branches.
4. Processes all targets in order; if any target fails, `arbor` exits with code 1
   after reporting errors.

When `--force` (or `-f`) is passed, `remove` force-removes dirty worktrees before
deleting the branch.

## What `checkout` does

1. Resolves `[worktree]` as a linked worktree path or unique directory name.
   When omitted, `checkout` uses the current worktree if you run it inside one.
2. Reads the branch currently checked out in that worktree.
3. Refuses to proceed if either the worktree checkout or the main repo checkout
   has uncommitted changes.
4. Detaches the worktree, switches the main repo checkout onto that branch, and
   removes the old linked worktree checkout.

## What `convert-to-worktree` does

1. Requires you to run it from the main repo checkout on a named branch.
2. Refuses to proceed when the main checkout has uncommitted changes.
3. Chooses the branch to leave in the main checkout from `--base`, then
   `origin/HEAD`, then local `main` or `master`.
4. Creates a new linked worktree directory, defaulting to a sibling
   `wt-<branch>` path when `[worktree]` is omitted.
5. Switches the main checkout to the base branch and moves the original branch
   into the new worktree.

## What `push-force` does

1. Resolves the current local branch and refuses to run from a detached `HEAD`.
2. Uses that branch's configured upstream remote/branch when available.
3. Falls back to `origin/<current-branch>` when no upstream is configured.
4. If there is no `origin`, falls back to the only configured remote when there
   is exactly one remote.
5. Runs `git push --force-with-lease <remote> HEAD:<branch>`.

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

# remove a local branch, also removing its linked worktree if present
arbor remove feature/my-branch

# remove a linked worktree by path or unique directory name
arbor remove ../wt-feature-my-branch
arbor remove wt-feature-my-branch

# remove multiple targets in one command
arbor remove feature/my-branch wt-feature-another

# force-remove a dirty worktree while removing its branch
arbor remove feature/my-branch --force

# move a linked worktree branch back into the main repo checkout
arbor checkout ../wt-feature-my-branch

# run from inside a linked worktree and convert the current checkout
arbor checkout

# move the current branch out of the main repo and into a default worktree path
arbor convert-to-worktree

# do the same move but pick the destination path and base branch explicitly
arbor convert-to-worktree ../wt-feature-my-branch --base main

# force-push the current branch with lease to its upstream/origin branch
arbor push-force
```

## Exit codes

- `0`: cleanup completed successfully (including no-op when nothing is merged)
- `1`: one or more worktrees/branches failed to remove
