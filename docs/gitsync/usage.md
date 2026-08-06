# `gitsync` usage

`gitsync` conservatively synchronizes a configured set of Git repositories. Each repository can pull and push, or operate in pull-only mode. It never resets, discards, force-pushes, or auto-commits ordinary user changes.

## Configuration

The default configuration is `~/.config/gitsync/agcron.json`:

```json
{
  "repos": [
    {
      "name": "agents",
      "path": "/Users/kevinlin/agents",
      "repo": "git@github.com:example/agents.git",
      "sync_schedule": "*/10 * * * *",
      "mode": "pull"
    }
  ]
}
```

Every entry must contain `name`, absolute `path`, `repo`, and `sync_schedule`. The optional `mode` is either `push/pull` or `pull`; when omitted, it defaults to `push/pull` for compatibility. Names and paths must be unique. Schedules are numeric, five-field cron expressions (`minute hour day-of-month month day-of-week`) supporting `*`, lists, ranges, and steps. Sunday is `0` or `7`. As in cron, day-of-month and day-of-week use OR semantics when both are restricted.

- `push/pull` fetches and merges upstream commits, then pushes local commits. Both the `origin` fetch and push URLs must identify the configured `repo`.
- `pull` fetches and merges upstream commits but never pushes. Only the `origin` fetch URL is validated, and JSON results report `"push": "skipped"`.

## Commands

```bash
gitsync validate
gitsync sync --due
gitsync sync --all
gitsync sync --force
gitsync sync --name agents
gitsync --config /path/to/agcron.json sync --all
```

`--due` claims each matching repository once per local clock minute. `--all` and its manual-friendly alias `--force` ignore schedules and sync every configured repository. Here, “force” only forces an immediate run: it never overrides the configured mode or enables Git force-push, reset, discard, or safety-check bypasses. `--name` selects one configured repository. Results are JSON; exit `0` means all selected repositories synced, `1` means at least one repository was safely blocked, and `2` means the command or configuration was invalid.

## Scheduling with launchd

No resident daemon is needed. Generate a macOS launch agent that wakes once a minute and lets `gitsync sync --due` evaluate each cron schedule:

```bash
mkdir -p ~/Library/LaunchAgents
gitsync launchd-plist > ~/Library/LaunchAgents/com.kevinlin.gitsync.plist
launchctl bootstrap "gui/$(id -u)" ~/Library/LaunchAgents/com.kevinlin.gitsync.plist
launchctl kickstart -k "gui/$(id -u)/com.kevinlin.gitsync"
```

To replace an existing registration, boot it out first, regenerate the plist, and bootstrap it again:

```bash
launchctl bootout "gui/$(id -u)/com.kevinlin.gitsync"
```

The generated plist uses the resolved CLI and config paths. Logs go to `~/Library/Logs/com.kevinlin.gitsync.log` and `.error.log`. Scheduled runs keep claim and lock files under `~/.cache/gitsync`.

## Safety behavior

- A missing path is cloned from the configured `repo`. An existing non-repository path is blocked and left untouched.
- The current branch must have an `origin` upstream, and `origin` must identify the configured repository. `push/pull` validates the fetch and push URLs; `pull` validates only the fetch URL. SSH and HTTPS URLs for the same host/path compare equally, but an SSH host alias (for example `github.com-personal`) must be written exactly as configured locally.
- Detached HEADs and dirty worktrees, including untracked files, are blocked before fetch or merge in both modes.
- Remote commits are fetched and fast-forwarded where possible. Diverged committed histories are merged normally; no-op pulls and pushes succeed.
- A push rejected because the remote advanced gets one fetch/merge/push retry. A second rejection is an exact blocker. Nothing is force-pushed.
- Authentication failures are reported as blockers without changing credentials.
- Locks are keyed by canonical repository path, so differently named config entries cannot run concurrently against the same worktree.
- If a merge conflicts, `codex exec` runs from that repository with a prompt limited to the current sync conflict. The sync resumes only after Codex completes the merge and leaves no unmerged paths or dirty worktree; otherwise the precise conflict state is preserved and reported as a blocker. In `pull` mode, Codex uses its workspace-write sandbox, the prompt forbids remote mutation, and the resolver environment blocks Git push/send-pack operations with a failing pre-push hook; a completed merge remains local.
