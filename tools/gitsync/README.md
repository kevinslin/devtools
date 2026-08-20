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
      "post_sync": [
        ["~/code/devtools/tools/gitsync/scripts/chezmoi-post-sync"],
        ["~/code/devtools/tools/gitsync/scripts/launchd-sync"]
      ]
    }
  ]
}
```

Every entry must contain `name`, `path`, `repo`, and `sync_schedule`. The `path` must be absolute after expanding a leading `~`, so `~/agents` is valid; shell variables such as `$HOME/agents` are not expanded. The optional `mode` is either `push/pull` or `pull`; when omitted, it defaults to `push/pull` for compatibility. The optional `post_sync` accepts either one non-empty argument array, such as `["script", "--arg"]`, or a non-empty ordered array of argument arrays, such as `[["first"], ["second", "--arg"]]`. Every argument array must be non-empty and contain only non-empty strings; mixed single-command and multi-command shapes are invalid. Existing single-command configurations remain valid and unchanged. Names and paths must be unique. Schedules are numeric, five-field cron expressions (`minute hour day-of-month month day-of-week`) supporting `*`, lists, ranges, and steps. Sunday is `0` or `7`. As in cron, day-of-month and day-of-week use OR semantics when both are restricted.

- `push/pull` fetches and merges upstream commits, then pushes local commits. Both the `origin` fetch and push URLs must identify the configured `repo`.
- `pull` fetches and merges upstream commits but never pushes. Only the `origin` fetch URL is validated, and JSON results report `"push": "skipped"`.

## Post-sync hooks

When configured, `post_sync` runs after every successful Git synchronization, including no-op pulls and newly cloned repositories. A single argument array runs one command; an array of argument arrays runs every command in its configured order.

Each command runs directly without a shell, with the synchronized repository as its working directory. A leading `~` is expanded only in each hook's executable path (`argv[0]`); relative executable paths such as `./scripts/post-sync` are resolved from that repository. Hook arguments and shell variables remain literal.

Hooks inherit the process environment plus:

- `GITSYNC_REPO_PATH`: absolute, canonical repository path.
- `GITSYNC_REPO_NAME`: configured repository name.
- `GITSYNC_OLD_HEAD`: commit before fetching and merging.
- `GITSYNC_NEW_HEAD`: commit after synchronization.

For a newly cloned repository, `GITSYNC_OLD_HEAD` is the clone's initial checked-out commit; it normally equals `GITSYNC_NEW_HEAD`. Every hook in the sequence receives the same repository context. In `pull` mode, every hook also inherits the same Git push/send-pack guard used for conflict resolution. This prevents ordinary or accidental Git pushes, but is not a security boundary: hooks execute trusted code and a deliberately malicious hook can bypass the guard. Configure only hooks you trust.

The sequence stops at the first failing or missing hook; later hooks do not run. The failure blocks the repository sync, reports its error, and releases that repository's scheduled claim so the same clock-minute run can retry. A retry performs a new synchronization and starts the configured hook sequence from the beginning, so hooks that already succeeded may run again. Ordinary repository safety blockers retain their existing once-per-minute claim.

### Example: reconcile `kevinlin-agents` with chezmoi

The configuration above first runs the repository-owned `~/code/devtools/tools/gitsync/scripts/chezmoi-post-sync` executable after each successful pull of `kevinlin-agents`, followed by `~/code/devtools/tools/gitsync/scripts/launchd-sync`. The agents repository's `agcron.json` template preserves those portable home-relative paths. The first hook explicitly selects `~/agents` as its standalone chezmoi source; `.chezmoiroot` resolves the managed source directory to `~/agents/config`, and `config/.chezmoiignore` keeps repository-local `AGENTS.md` and `README.md` documentation out of the home directory.

For each managed file, the hook compares three versions: the rendered source at `GITSYNC_OLD_HEAD`, the rendered source at `GITSYNC_NEW_HEAD`, and the current machine-local destination.

- Incoming-only changes are applied through chezmoi, preserving private-file permissions.
- Machine-local-only changes are retained.
- Independent local and incoming changes are backed up, then reconciled with a three-way merge.
- Overlapping edits, binary conflicts, unsupported symlinks, and existing files without a safe baseline stop without overwriting local data. Blocking destination symlinks are backed up without following them; directories are never copied recursively.
- Unresolved conflicts invoke the installed `slack-notify` helper with the hostname, affected targets, and backup location. Notifications are deduplicated across retries, and pending merge baselines survive subsequent upstream updates.

Backups and conflict state live under `~/.local/state/kevinlin-agents/chezmoi-post-sync/`; backup directories are private. Scheduled hooks also resolve Homebrew's `chezmoi` and `slack-post` when launchd supplies only a minimal `PATH`.

After changing the repository-owned hooks or gitsync configuration, verify both executables exist before activating the configuration that references them:

```bash
test -x "$HOME/code/devtools/tools/gitsync/scripts/chezmoi-post-sync"
test -x "$HOME/code/devtools/tools/gitsync/scripts/launchd-sync"
chezmoi --source "$HOME/agents" apply "$HOME/.config/gitsync/agcron.json"
gitsync --config "$HOME/.config/gitsync/agcron.json" validate
```

Do not use a bare or repository-wide `chezmoi apply` to activate the hook: unrelated machine-local configuration may differ. The repository must also be clean before scheduled synchronization can run.

### launchd-sync

`launchd-sync` runs after `chezmoi-post-sync` and reconciles owned LaunchAgents
against the shared placement policy. Both executables are owned by
`~/code/devtools/tools/gitsync/scripts/`; only the policy
`~/.config/gitsync/launchd-jobs.json` and staged plist files under
`~/.config/gitsync/` are chezmoi-managed configuration. The policy alone
declares each job's ownership and `all_machine` or `primary_only` placement;
jobs are not selected by hardcoded label prefixes. In `pull` mode, both scripts
inherit the existing Git push guard and cannot perform ordinary pushes.

## Commands

```bash
gitsync validate
gitsync status
gitsync status --filter dirty=true
gitsync status --filter dirty=false
gitsync sync --due
gitsync sync --all
gitsync sync --force
gitsync sync --name agents
gitsync --config /path/to/agcron.json sync --all
gitsync daemon --config /path/to/agcron.json --interval 15
gitsync --config /path/to/agcron.json daemon --interval 15
```

`--due` claims each matching repository once per local clock minute. `--all` and its manual-friendly alias `--force` ignore schedules and sync every configured repository. Here, “force” only forces an immediate run: it never overrides the configured mode or enables Git force-push, reset, discard, or safety-check bypasses. `--name` selects one configured repository. One-shot sync results are JSON; exit `0` means all selected repositories synced, `1` means at least one repository was safely blocked, and `2` means the command or configuration was invalid.

## Foreground daemon

`gitsync daemon` stays in the foreground so launchd, supervisord, or another
existing process supervisor can own its lifecycle:

```bash
gitsync daemon --config "$HOME/.config/gitsync/agcron.json" --interval 15
```

The first cycle runs immediately; later cycles run after the requested interval,
which defaults to 15 seconds and must be a positive, finite number. Each cycle
reloads the configuration and performs the existing `sync --due` operation.
The polling interval does not replace or bypass each repository's cron
schedule: existing local-clock-minute claims prevent repeated synchronization
during the same scheduled minute, and repository locks, pull-only protections,
Git authorization inheritance, post-sync hooks, and structured daily run logs
retain their normal behavior. Configuration changes take effect on a later
cycle without restarting the supervisor or daemon.

Per-cycle JSON sync results are written to stdout; lifecycle messages and
errors go to stderr. A blocked repository or invalid configuration is reported
without terminating the daemon, and the next cycle retries; fixing the
configuration therefore restores synchronization without restarting the
service. Unexpected process failures remain visible to the supervisor so its
normal restart policy can apply. `SIGTERM` and `SIGINT` interrupt an idle wait
promptly or allow an active sync cycle to finish, then exit successfully.

Run only one scheduler for the same profile. On macOS, one persistent launchd
job supervises the daemon while gitsync evaluates every repository's cron
schedule itself. Claims and locks still protect repositories if schedulers
temporarily overlap during migration, but concurrent schedulers are unnecessary.

## Daily run logs

Every `gitsync sync` invocation, including each daemon polling cycle, appends
one JSON record to:

```text
/tmp/gitsync-YYYY-MM-DD.log
```

The filename uses the machine's local date. Each newline-delimited record
includes a timezone-aware timestamp, configuration path, requested selection,
exit code, overall status, and either per-repository results or the
configuration error. Successful, blocked, zero-repository, manual, and
scheduled syncs are all recorded. Read-only commands such as `status`,
`validate`, and `launchd-plist` do not create log entries.

Daily log files are append-only and private (`0600`). Unsafe symlinks,
non-regular files, multiply linked files, files owned by another user, or
files readable by other users are refused. Logging failures produce a concise
warning without changing the sync result. `GITSYNC_LOG_DIR` can override
`/tmp` for an isolated test or explicitly managed deployment.

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

Use `gitsync status --filter dirty=true` to list only repositories with staged,
modified, or untracked changes, or `gitsync status --filter dirty=false` to list
only clean repositories. Both filters preserve configured repository ordering;
missing or invalid repositories have unknown dirtiness and match neither.
Unfiltered `gitsync status` continues to include every configured repository.
Filters must have the form `KEY=VALUE`; currently `dirty` is the only supported
key and its value must be exactly `true` or `false`. Invalid filters print an
actionable error and exit with status `2`.

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

`gitsync launchd-plist` generates one persistent macOS LaunchAgent that starts
the foreground daemon immediately and keeps it running. The daemon polls every
15 seconds, reloads its configuration on each cycle, and evaluates each
repository's existing cron schedule; launchd supervises the process rather than
managing individual synchronization runs. Manual one-shot commands such as
`gitsync sync --due`, `gitsync sync --all`, and `gitsync sync --name agents`
remain supported.

For an unmanaged LaunchAgent, generate and register the single
`com.kevinlin.gitsync` label:

```bash
mkdir -p "$HOME/Library/LaunchAgents"
gitsync launchd-plist > "$HOME/Library/LaunchAgents/com.kevinlin.gitsync.plist"
plutil -lint "$HOME/Library/LaunchAgents/com.kevinlin.gitsync.plist"
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.kevinlin.gitsync.plist"
launchctl print "gui/$(id -u)/com.kevinlin.gitsync"
```

The generated plist uses the resolved executable and configuration paths,
enables `RunAtLoad` and `KeepAlive`, and has no `StartInterval`:

```xml
<key>Label</key>
<string>com.kevinlin.gitsync</string>
<key>ProgramArguments</key>
<array>
  <string>/Users/kevinlin/.local/bin/gitsync</string>
  <string>daemon</string>
  <string>--config</string>
  <string>/Users/kevinlin/.config/gitsync/agcron.json</string>
  <string>--interval</string>
  <string>15</string>
</array>
<key>RunAtLoad</key>
<true/>
<key>KeepAlive</key>
<true/>
```

Existing `EnvironmentVariables`, the executable search path, Git authorization,
`Background` process classification, and log destinations are preserved.
Launchd captures daemon stdout and stderr in
`~/Library/Logs/com.kevinlin.gitsync.log` and `.error.log`; each daemon cycle
also appends its structured sync result to `/tmp/gitsync-YYYY-MM-DD.log`.
Scheduled claims and repository locks remain under
`$XDG_STATE_HOME/gitsync/`, defaulting to `~/.local/state/gitsync/`.

### Migrating an existing managed macOS LaunchAgent

When the existing LaunchAgent belongs to the `~/agents` chezmoi source, update
its source-of-truth template at
`~/agents/config/Library/LaunchAgents/com.kevinlin.gitsync.plist.tmpl` to match
the daemon configuration above. Preserve the existing label,
`EnvironmentVariables`, executable search path, log paths, and Git
authorization. Review and apply only that specific destination, then replace
the existing registration under the same label:

```bash
chezmoi --source "$HOME/agents" diff \
  "$HOME/Library/LaunchAgents/com.kevinlin.gitsync.plist"
chezmoi --source "$HOME/agents" apply --parent-dirs \
  "$HOME/Library/LaunchAgents/com.kevinlin.gitsync.plist"
plutil -lint "$HOME/Library/LaunchAgents/com.kevinlin.gitsync.plist"
launchctl bootout "gui/$(id -u)/com.kevinlin.gitsync"
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.kevinlin.gitsync.plist"
launchctl print "gui/$(id -u)/com.kevinlin.gitsync"
```

Verify that `launchctl print` reports the existing
`com.kevinlin.gitsync` service running with one daemon process, that its
arguments include `daemon --config` and `--interval 15`, and that no
`StartInterval` remains. Inspect the launchd output and daily structured log to
confirm successive daemon cycles and normal repository scheduling.

Run migration from a separate shell after any active gitsync post-sync hook
finishes; do not unload the running service from its own hook. Never perform a
bare or repository-wide `chezmoi apply`, replace unrelated LaunchAgents, or
register a second gitsync label while the previous scheduler remains active.

### Supervised foreground daemon on a Linux DevBox

On a Linux DevBox, the existing user-owned supervisord can run the
`kevinlin-gitsync` program alongside unrelated application programs. Its
supervisor configuration is
`/home/dev-user/.config/supervisor/supervisord.conf`, and the existing gitsync
program drop-in is
`/home/dev-user/.config/supervisor/conf.d/kevinlin-gitsync.conf`. Systemd and
cron are unnecessary; restarting or replacing supervisord can lose the
private Git authorization already present in its process environment.

The DevBox uses its own `~/.config/gitsync/devbox.json` profile. Do not replace
it with the shared `agcron.json`: that profile contains laptop paths that do
not exist on the DevBox. The Linux-only chezmoi source files are:

- `~/agents/config/dot_config/private_gitsync/private_devbox.json.tmpl` for
  `~/.config/gitsync/devbox.json`.
- `~/agents/config/dot_config/private_supervisor/private_conf.d/private_kevinlin-gitsync.conf.tmpl`
  for `~/.config/supervisor/conf.d/kevinlin-gitsync.conf`.

The DevBox profile preserves the existing pull-only `agents`, `skills-local`,
and `skills-public` entries and adds the existing `~/code/devtools` checkout as
a pull-only `devtools` entry. The skills use their existing checkout paths and
retain their existing post-sync hooks. The `agents` hook performs a
targeted chezmoi apply of `agcron.json`, `devbox.json`, and the supervisor
drop-in only; it never restarts the supervisor or its own gitsync process.
Review and activate changed supervisor directives separately.

First update the DevBox's existing devtools checkout from its public
`https://github.com/kevinslin/devtools.git` remote and ensure that the
installed `gitsync` executable resolves the updated version. Before changing
the existing supervisor program, confirm that the executable supports the
`daemon` subcommand, preview the two Linux-managed targets, and apply only
those files:

```bash
"$HOME/.local/bin/gitsync" daemon --help
"$HOME/.local/bin/chezmoi" --source "$HOME/agents" diff \
  "$HOME/.config/gitsync/devbox.json" \
  "$HOME/.config/supervisor/conf.d/kevinlin-gitsync.conf"
"$HOME/.local/bin/chezmoi" --source "$HOME/agents" apply --parent-dirs \
  "$HOME/.config/gitsync/devbox.json" \
  "$HOME/.config/supervisor/conf.d/kevinlin-gitsync.conf"
"$HOME/.local/bin/gitsync" \
  --config "$HOME/.config/gitsync/devbox.json" validate
```

On this DevBox, `$HOME` is `/home/dev-user`. Stop without changing the existing
supervisor program if `daemon --help` or profile validation fails. A valid
configuration only confirms its schema; inspect the configured checkouts and
observed synchronization results separately.

The managed supervisor drop-in replaces the existing polling wrapper with the
foreground daemon while preserving the existing program label and other
directives:

```ini
[program:kevinlin-gitsync]
command=/home/dev-user/.local/bin/gitsync daemon --config /home/dev-user/.config/gitsync/devbox.json --interval 15
; Keep every other existing program directive unchanged.
```

Keep the existing socket at
`/home/dev-user/.config/supervisor/supervisor.sock`, working directory
`/home/dev-user/agents`, `HOME=/home/dev-user`, existing `PATH`, process
environment, restart policy, stop settings, and sibling programs unchanged.
Preserve the existing `/home/dev-user/.local/state/gitsync/supervisor.log` and
`supervisor.err` log paths. Refresh only the existing gitsync program through
the already-running supervisor:

```bash
supervisorctl -c "$HOME/.config/supervisor/supervisord.conf" reread
supervisorctl -c "$HOME/.config/supervisor/supervisord.conf" \
  update kevinlin-gitsync
supervisorctl -c "$HOME/.config/supervisor/supervisord.conf" \
  status kevinlin-gitsync
tail -n 20 "$HOME/.local/state/gitsync/supervisor.log"
tail -n 20 "$HOME/.local/state/gitsync/supervisor.err"
```

Do not start another supervisord or gitsync program, restart the existing
supervisor, disturb unrelated application programs, copy or print credentials,
or overwrite inherited Git authorization. Direct SSH shells may
not inherit the supervisor's private Git authorization, so a manual sync from
such a shell does not establish what the supervised daemon can access. Verify
that the existing program reports `RUNNING`, its command uses `devbox.json`,
and its logs show successive scheduling cycles and successful repository
synchronization. Machine-local edits and dirty repositories remain protected
by gitsync's existing safety checks; report authentication, checkout, or hook
failures without claiming the affected repository synchronized.

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
