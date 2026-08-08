# Configsync

Configsync is a proposed Ansible-based workflow for keeping Mac configuration
consistent while preserving existing ownership by chezmoi, gitsync, agent-sync,
and Homebrew. It is currently in the planning stage; no playbook, configuration,
or executable has been implemented yet.

When implemented, portable playbooks and task sources belong in this project,
while runtime settings belong under `~/.config/configsync/`. Managed settings
and any optional LaunchAgent source belong to the `~/agents/config/` chezmoi
source, not this repository.

- [Feature specification](specs/spec.md)
