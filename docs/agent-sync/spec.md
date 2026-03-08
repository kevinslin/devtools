# `agent-sync` design

## Goal

Provide a simple, local-first way to keep agent configuration in sync across multiple computers using plain git, without requiring a background service or custom server.

## Topology

Each computer has:

- a live config directory, such as `~/.codex`
- a dedicated local clone of the shared git repo
- a local state file storing the last synced snapshot

The remote git repo is the transport and history layer, not the only source of truth during a run.

## Core algorithm

The tool uses a file-level three-way comparison:

- `base`: the last synced snapshot from the local state file
- `source`: the current live-folder snapshot
- `repo`: the current repo-clone snapshot after pulling latest remote changes

Per tracked file:

- if `source == repo`, nothing changed
- if `source == base`, only repo changed, so copy repo to source
- if `repo == base`, only source changed, so copy source to repo
- otherwise both changed the same file, so report a conflict

This keeps the implementation small while still handling the important two-way cases safely.

## Why keep a local state file

Git alone tells you what changed in the repo clone, but it does not tell you whether the live config folder also changed since the last successful sync.

The local state file solves that by recording:

- the last synced commit
- the last synced file fingerprints for the tracked subset

This gives the script the missing third side needed for conflict detection.

## Conflict model

The tool intentionally avoids line-level merges. It resolves at file granularity because agent config trees are usually small and mostly composed of discrete files.

Same-file edits on both sides are treated as conflicts. Recovery is explicit:

- rerun with `--force source` to keep the live-folder version
- rerun with `--force repo` to keep the git version

## Git behavior

The repo clone is expected to be clean and dedicated to sync.

Each run:

1. checks out the configured branch
2. runs `git pull --rebase`
3. copies source-owned changes into the repo clone
4. commits and pushes if needed
5. copies repo-owned changes into the live folder

This keeps the live folder aligned with the final repo state after a successful run.

## Dry run

`--dry-run` reuses the same planning logic but stops before any side effects.

It does not:

- copy files
- update the state file
- switch branches
- pull, commit, or push

To keep it side-effect free, the preview is computed against the repo clone's current checkout. The clone must already be on the configured branch.

## Scope limits

Deliberate non-goals:

- preserving symlinks as symlinks
- line-by-line text merges
- syncing file permissions beyond executable-bit preservation through `copy2`
- managing initial repo creation or host-specific secret material

Those constraints keep the tool predictable and easy to audit.
