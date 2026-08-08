# `gitsync` usage

`gitsync` conservatively synchronizes a configured set of Git repositories. Each repository can pull and push, or operate in pull-only mode. It never resets, discards, force-pushes, or auto-commits ordinary user changes.

## Configuration

The default configuration is `~/.config/gitsync/agcron.json`:

```json
{
  "repos": [
    {
      "name": "agents",
      "path": "~/agents",
      "repo": "https://github.com/openai/kevinlin-agents.git",
      "sync_schedule": "*/10 * * * *",
      "mode": "pull",
      "post_sync": ["/Users/kevinlin/.config/gitsync/scripts/chezmoi-post-sync"]
    }
  ]
}
```

Every entry must contain `name`, `path`, `repo`, and `sync_schedule`. The `path` must be absolute after expanding a leading `~`, so `~/agents` is valid; shell variables such as `$HOME/agents` are not expanded. The optional `mode` is either `push/pull` or `pull`; when omitted, it defaults to `push/pull` for compatibility. The optional `post_sync` must be a non-empty argument array whose entries are non-empty strings. Names and paths must be unique. Schedules are numeric, five-field cron expressions (`minute hour day-of-month month day-of-week`) supporting `*`, lists, ranges, and steps. Sunday is `0` or `7`. As in cron, day-of-month and day-of-week use OR semantics when both are restricted.

- `push/pull` fetches and merges upstream commits, then pushes local commits. Both the `origin` fetch and push URLs must identify the configured `repo`.
- `pull` fetches and merges upstream commits but never pushes. Only the `origin` fetch URL is validated, and JSON results report `"push": "skipped"`.

## Post-sync hooks

When configured, `post_sync` runs after every successful Git synchronization, including no-op pulls and newly cloned repositories. The command runs directly without a shell, with the synchronized repository as its working directory. Relative executable paths such as `./scripts/post-sync` are therefore resolved from that repository. Hook arguments do not expand `~` or shell variables; use an absolute path for hooks installed outside the repository.

Hooks inherit the process environment plus:

- `GITSYNC_REPO_PATH`: absolute, canonical repository path.
- `GITSYNC_REPO_NAME`: configured repository name.
- `GITSYNC_OLD_HEAD`: commit before fetching and merging.
- `GITSYNC_NEW_HEAD`: commit after synchronization.

For a newly cloned repository, `GITSYNC_OLD_HEAD` is the clone's initial checked-out commit; it normally equals `GITSYNC_NEW_HEAD`. In `pull` mode, hooks inherit the same Git push/send-pack guard used for conflict resolution. This prevents ordinary or accidental Git pushes, but is not a security boundary: hooks execute trusted code and a deliberately malicious hook can bypass the guard. Configure only hooks you trust. A failing or missing hook blocks the repository sync, reports its error, and releases that repository's scheduled claim so the same clock-minute run can retry; ordinary repository safety blockers retain their existing once-per-minute claim.

### Example: reconcile `kevinlin-agents` with chezmoi

The configuration above runs the chezmoi-managed `~/.config/gitsync/scripts/chezmoi-post-sync` executable after each successful pull of `kevinlin-agents`. The agents repository's `agcron.json` template renders the correct absolute home-directory path for each machine. The hook explicitly selects `~/agents` as its standalone chezmoi source; `.chezmoiroot` resolves the managed source directory to `~/agents/config`, and `config/.chezmoiignore` keeps repository-local `AGENTS.md` and `README.md` documentation out of the home directory.

For each managed file, the hook compares three versions: the rendered source at `GITSYNC_OLD_HEAD`, the rendered source at `GITSYNC_NEW_HEAD`, and the current machine-local destination.

- Incoming-only changes are applied through chezmoi, preserving private-file permissions.
- Machine-local-only changes are retained.
- Independent local and incoming changes are backed up, then reconciled with a three-way merge.
- Overlapping edits, binary conflicts, unsupported symlinks, and existing files without a safe baseline stop without overwriting local data. Blocking destination symlinks are backed up without following them; directories are never copied recursively.
- Unresolved conflicts invoke the installed `slack-notify` helper with the hostname, affected targets, and backup location. Notifications are deduplicated across retries, and pending merge baselines survive subsequent upstream updates.

Backups and conflict state live under `~/.local/state/kevinlin-agents/chezmoi-post-sync/`; backup directories are private. Scheduled hooks also resolve Homebrew's `chezmoi` and `slack-post` when launchd supplies only a minimal `PATH`.

After changing the repository-managed hook or gitsync configuration, install the executable before activating the configuration that references it:

```bash
chezmoi --source "$HOME/agents" apply --parent-dirs \
  "$HOME/.config/gitsync/scripts/chezmoi-post-sync"
chezmoi --source "$HOME/agents" apply "$HOME/.config/gitsync/agcron.json"
gitsync --config "$HOME/.config/gitsync/agcron.json" validate
```

Do not use a bare or repository-wide `chezmoi apply` to activate the hook: unrelated machine-local configuration may differ. The repository must also be clean before scheduled synchronization can run.

## Commands

```bash
gitsync validate
gitsync status
gitsync sync --due
gitsync sync --all
gitsync sync --force
gitsync sync --name agents
gitsync --config /path/to/agcron.json sync --all
```

`--due` claims each matching repository once per local clock minute. `--all` and its manual-friendly alias `--force` ignore schedules and sync every configured repository. Here, “force” only forces an immediate run: it never overrides the configured mode or enables Git force-push, reset, discard, or safety-check bypasses. `--name` selects one configured repository. Results are JSON; exit `0` means all selected repositories synced, `1` means at least one repository was safely blocked, and `2` means the command or configuration was invalid.

## Repository status

`gitsync status` lists every configured repository without fetching, syncing,
creating a missing checkout, or writing state:

```json
{
  "status": "ok",
  "repos": [
    {
      "name": "agents",
      "path": "/Users/kevinlin/agents",
      "repo": "https://github.com/openai/kevinlin-agents.git",
      "sync_schedule": "*/10 * * * *",
      "mode": "pull",
      "last_fetched": "2026-08-08T11:30:00-07:00",
      "dirty": false,
      "status": "ok"
    }
  ]
}
```

`last_fetched` is the timestamp of the most recent successful fetch, even when
a later merge, push, or post-sync hook fails. Existing repositories that have
not yet recorded gitsync state fall back to their Git `FETCH_HEAD` timestamp;
repositories without any observed fetch report `null`. A missing checkout is
reported with `status: "missing"` and `dirty: null`; invalid repository paths
are reported without attempting to repair them.

Fetch history, scheduled-run claims, and repository locks live in
`$XDG_STATE_HOME/gitsync/`, or `~/.local/state/gitsync/` when `XDG_STATE_HOME`
is unset. `GITSYNC_STATE_DIR` overrides the complete directory for isolated
tests or an explicitly managed deployment.

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

The generated plist uses the resolved CLI and config paths. Logs go to `~/Library/Logs/com.kevinlin.gitsync.log` and `.error.log`. Scheduled runs keep claim and lock files under `$XDG_STATE_HOME/gitsync/`, defaulting to `~/.local/state/gitsync/`.

## Safety behavior

- A missing path is cloned from the configured `repo`. An existing non-repository path is blocked and left untouched.
- The current branch must have an `origin` upstream, and `origin` must identify the configured repository. `push/pull` validates the fetch and push URLs; `pull` validates only the fetch URL. SSH and HTTPS URLs for the same host/path compare equally, but an SSH host alias (for example `github.com-personal`) must be written exactly as configured locally.
- Detached HEADs and dirty worktrees, including untracked files, are blocked before fetch or merge in both modes.
- Remote commits are fetched and fast-forwarded where possible. Diverged committed histories are merged normally; no-op pulls and pushes succeed.
- A push rejected because the remote advanced gets one fetch/merge/push retry. A second rejection is an exact blocker. Nothing is force-pushed.
- Authentication failures are reported as blockers without changing credentials.
- Locks are keyed by canonical repository path, so differently named config entries cannot run concurrently against the same worktree.
- Configured post-sync hooks execute while the repository lock remains held; shell metacharacters in arguments are passed literally.
- If a merge conflicts, `codex exec` runs from that repository with a prompt limited to the current sync conflict. The sync resumes only after Codex completes the merge and leaves no unmerged paths or dirty worktree; otherwise the precise conflict state is preserved and reported as a blocker. In `pull` mode, Codex uses its workspace-write sandbox, the prompt forbids remote mutation, and the resolver environment blocks Git push/send-pack operations with a failing pre-push hook; a completed merge remains local.
