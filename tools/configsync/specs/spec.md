# Feature Spec: Ansible-first computer configuration sync

**Date:** 2026-08-06
**Status:** Planning
**Owner:** `devtools/tools/configsync`

## Problem and Decision

Keep multiple Macs configured consistently without replacing tools that already own dotfiles, Git repositories, packages, agent settings, and launchd jobs.

Build `configsync` as an Ansible playbook that runs locally on each computer. Chezmoi owns dotfiles, existing `gitsync` owns repository synchronization and its LaunchAgent, Homebrew owns packages, and existing `agent-sync` is optional. Ansible supplies sequencing, conditional execution, idempotency, and check mode. Do not introduce a provider framework, dependency engine, new synchronization service, or required custom CLI.

## Scope

**Changes**

- Add a portable local playbook with safe in-code defaults, small task files, operator documentation, and focused tests; keep runtime configuration and optional LaunchAgent source in the agents repository's chezmoi source.
- Support independent `self` and `work` profiles, host-local overrides, read-only health checks, and optional macOS scheduling.
- Preserve a future Windows boundary without claiming native Windows support.

**Does not change**

- Existing `gitsync` code, configuration format, per-repository `mode`, repository locks, conflict handling, or `com.kevinlin.gitsync` LaunchAgent.
- Existing chezmoi/`agent-sync` behavior, canonical skill watcher, authentication, SSH keys, unrelated LaunchAgents, or user crontab.
- Native Windows execution, whole-directory mirroring, forced package upgrades, package cleanup, Git reset/stash/force-push, or unattended privilege escalation.

## Contract

### Configuration and invocation

Portable, nonsecret implementation defaults live in the playbook's source variables. Runtime settings live outside the devtools checkout at `~/.config/configsync/config.yaml`; an optional `~/.config/configsync/local.yaml` supplies host-specific overrides. Keep the portable source of managed configuration in `~/agents/config/` and synchronize it through that repository's explicitly selected chezmoi source. Sensitive local configuration uses mode `0600`; never commit plaintext credentials. Merge playbook defaults, runtime configuration, platform values, selected `self`, selected `work`, then host-local overrides. `self` and `work` are independent trust domains; work-only values cannot be committed to personal repositories.

```yaml
profiles: [self, work]
platform: mac
dotfiles:
  enabled: true
  source: "{{ ansible_env.HOME }}/code/Mackup"
repositories:
  enabled: true
  config: "{{ ansible_env.HOME }}/.config/gitsync/agcron.json"
agent_sync:
  enabled: false
  config: null
packages:
  brewfile: null
scheduler:
  enabled: false
```

Run the standard Ansible interface directly:

```bash
ansible-playbook -i localhost, -c local tools/configsync/playbooks/site.yml
ansible-playbook -i localhost, -c local tools/configsync/playbooks/site.yml --check
ansible-playbook -i localhost, -c local tools/configsync/playbooks/site.yml --tags status
ansible-playbook -i localhost, -c local tools/configsync/playbooks/site.yml --tags doctor
```

Tasks execute in fixed order: preflight, selected provider tasks, then explicitly enabled scheduler installation. There is no generic dependency graph. A future `tools/configsync/bin/configsync` wrapper is optional; if introduced, it only forwards to Ansible and must satisfy the [repository CLI documentation requirements](../../../AGENTS.md).

### Provider ownership

- **Preflight:** Require a supported macOS host, installed Ansible/chezmoi/selected provider executables, valid profile configuration, approved work-only inputs, and nonoverlapping destination ownership. Fail before mutation on tracked secrets, a dirty dotfiles source, missing selected configuration, or a destination claimed by multiple tools.
- **Dotfiles:** Explicitly select the approved chezmoi source for each managed target; devtool runtime configuration is owned by the `~/agents/config/` source, while any broader dotfiles source remains separately owned. Run source-scoped chezmoi status/verification, then apply only when drift is safe and the selected profile authorizes the source. Preserve templates and local edits; never mirror all of `~/.config`, `.ssh`, Codex auth/session state, or generated `.codex/skills`.
- **Git repositories:** Run `gitsync validate` and inspect the already installed `com.kevinlin.gitsync` LaunchAgent. Existing `gitsync` owns all repository operations and schedules. Preserve each repository's existing `mode`: `pull` never pushes; omitted `mode` defaults to `push/pull`. Do not add metadata to its JSON, invoke another repository scheduler, or manage its worktrees with Ansible Git tasks. [Current gitsync contract](../../gitsync/README.md).
- **Agent configuration:** Keep `agent_sync.enabled: false` until a machine-local, existing JSON configuration path is explicitly supplied. If enabled, call `agent-sync <config>`; check mode calls `agent-sync --dry-run <config>`. Reject overlapping `.codex/agents` ownership with chezmoi. No previously observed configuration path is assumed to exist. [Existing agent-sync contract](../../agent-sync/README.md).
- **Packages:** Skip package management until a Brewfile is explicitly configured. Compare with `brew bundle check --file=<path>` and install only missing declarations using `brew bundle install --no-upgrade --file=<path>`. `community.general.homebrew_bundle` does not exist; use Ansible built-ins and the Homebrew CLI unless a real collection dependency is intentionally added.
- **Scheduling:** Preserve the existing gitsync job exactly. Optional configuration reconciliation uses a separate `com.kevinlin.configsync` LaunchAgent whose source belongs to the agents repository's chezmoi source, not the devtools checkout. Use explicit executable paths, `PATH`, safe log locations, and quarter-hour `StartCalendarInterval`. Wrap scheduled apply/pull with `/usr/bin/lockf -k -t 0` so overlapping runs do not execute. If using `ansible-pull`, give it a dedicated, clean checkout; never use `--clean` or point it at a provider-managed worktree.

### Safety and failure behavior

Ansible `ansible.builtin.command` tasks do not automatically provide meaningful check-mode behavior. Read-only checks use `check_mode: false` with `changed_when: false`; mutating commands run only when `not ansible_check_mode`. Default previews use `--check`, never global `--diff`; sensitive tasks use `no_log: true` and `diff: false`.

The current chezmoi source contains a tracked plaintext `HOMEBREW_GITHUB_API_TOKEN` assignment. Revoke/rotate and remove that credential through separately authorized remediation before broader dotfile rollout; diagnostics must never print its value.

Provider failures report their resource and blocker. Independent selected tasks may continue, but installation of the configsync LaunchAgent requires all selected providers to pass, and any provider failure makes the overall run fail. Never overwrite dirty files, modify another provider's scheduler, weaken a pull-only repository, or copy authentication material.

macOS is the supported platform. Reject `platform: windows` before mutation: Ansible has no native Windows control node, and current `gitsync` imports Unix-only `fcntl`. Native Task Scheduler/WinGet or an approved WSL controller is separate work.

## Implementation

1. Document explicit Ansible installation and required built-in modules; Ansible is not currently installed. Do not add an Ansible Galaxy collection unless an actual collection-backed task requires one.
2. Add `tools/configsync/playbooks/site.yml` with nonsecret implementation defaults and focused playbook task files such as `tasks/preflight.yml`, `tasks/dotfiles.yml`, `tasks/repositories.yml`, `tasks/agent-sync.yml`, `tasks/packages.yml`, and `tasks/scheduler.yml`.
3. Load runtime settings from `~/.config/configsync/config.yaml`, apply optional `~/.config/configsync/local.yaml` overrides, and implement profile/platform selection with ordinary Ansible variables and conditions. Manage portable configuration through the `~/agents/config/` chezmoi source. Keep agent-sync and package management disabled until their required inputs exist.
4. Implement read-only status/doctor tags, safe check-mode probes, provider ownership checks, and the existing `gitsync` pull-mode preservation contract.
5. If scheduling is explicitly enabled, manage an opt-in `com.kevinlin.configsync` LaunchAgent from the agents repository's chezmoi source; manage only that label after successful provider checks. Do not add a plist or runtime configuration under `tools/configsync/`. A dedicated `ansible-pull` checkout is optional.
6. Expand `tools/configsync/README.md` and add `tests/test_configsync.py`. Update the repository `README.md` only if implementation also introduces an optional `tools/configsync/bin/configsync` entrypoint.

## Verification

| Required outcome | How to verify |
| --- | --- |
| Playbook structure is valid | After implementation, run `ansible-playbook -i localhost, -c local tools/configsync/playbooks/site.yml --syntax-check`. |
| Runtime configuration remains external | Confirm runtime files resolve under `~/.config/configsync/`, portable managed sources belong to `~/agents/config/`, and the devtools project has no runtime `config/` directory or LaunchAgent source. |
| No custom orchestration is introduced | Confirm standard Ansible commands work without a required wrapper, provider framework, dependency graph, or daemon. |
| Missing prerequisites are actionable | Simulate missing Ansible or an enabled provider executable and verify a clear bootstrap error before changes. |
| Profiles remain isolated | Exercise `self`, `work`, and both; reject work data from a personal source and overlapping owned destinations. |
| Preview is read-only and redacted | Run with `--check` against fixture providers; verify no Git push/pull, file write, package install, scheduler change, or secret disclosure. |
| gitsync preserves current behavior | Verify its config/plist remain unchanged, `gitsync validate` succeeds, and an existing `mode: pull` never changes or pushes. |
| Agent sync remains opt-in | Unconfigured agent-sync is skipped; an enabled missing config blocks; a configured preview passes the exact positional config path. |
| Packages are conservative | Missing Brewfile skips the role; missing packages install with `--no-upgrade`; cleanup and global upgrades never run. |
| Scheduling is isolated | Validate the agents-chezmoi-owned optional `com.kevinlin.configsync` plist, calendar trigger, nonblocking lock, and unchanged existing gitsync label. |
| Repeated application is idempotent | Run twice against isolated fixtures; the second run produces no provider changes or duplicate jobs. |
| Windows fails honestly | Set `platform: windows`; assert a precise unsupported-platform error before mutation. |
| Existing repository tests remain green | Run `python -m unittest discover -s tests`; never run `npm run precommit`. |

## Open Decisions

- Which approved work-owned source supplies work-only overlays?
- Should `.codex/agents` remain chezmoi-owned, or move to an explicitly configured `agent-sync` profile?
- Should scheduled runs use the local playbook or a separately approved `ansible-pull` checkout?

## Manual Notes

[keep this for the user to add notes. do not change between edits]

## Changelog
- [2026-08-06 14:54]: Recreated and simplified the feature spec around a local Ansible playbook and current gitsync pull-only behavior. (019fd4e3-8bc9-7430-8de2-cf64f5a82624 - 0d893c2)
