# AGENTS

Repository instructions for agents working in `/Users/kevinlin/code/devtools`.

## Project layout

Organize command-line tools under `tools/` and applications under `apps/`.
Each tool or application owns its project directory:

```text
tools/<project>/ or apps/<project>/
  README.md   # Human-facing documentation; required for every project.
  AGENTS.md   # Project-specific agent instructions, only when needed.
  bin/        # Project-owned executable entry points.
  config/     # Project-owned runtime configuration.
  docs/       # Supporting architecture, flow, or research documentation.
  specs/      # Project design and implementation specifications.
```

Create optional directories only when the project actually has content for
them. Project-specific implementation sources may also live under `src/`.

Keep the repository-root `README.md` as the concise project catalog. Root
`bin/` contains compatibility symlinks to tool or application executables
because existing shell environments, LaunchAgents, and shared tests rely on
those paths. Root `config/` may likewise retain narrowly scoped compatibility
symlinks for installed consumers. Preserve any installed application entry
paths under `apps/`. Shared tests, assets, package manifests, and repository-wide
instructions remain at the repository root.

## CLI documentation requirement

For every CLI in this project, keep `README.md` updated.

- Any new CLI added under `tools/<project>/bin/` or `apps/<project>/bin/` must
  be added to the `## CLI index` section in the repository-root `README.md`.
- Keep a compatibility symlink under root `bin/` when existing shell or launchd
  consumers need the stable command path.
- Use a single-line bullet per CLI (do not create per-tool markdown sections).
- Keep the `## Tool maturity` section in `README.md` present and current.
- Each line must include:
  - Maturity emoji and classification
  - CLI name
  - Canonical project entry point path (for example,
    `tools/<tool>/bin/<tool>`)
  - One-line description of what the CLI does
  - Link to its human-facing `tools/<tool>/README.md` or
    `apps/<application>/README.md`
- Use exactly one maturity marker per CLI entry:
  - `🌱 seed`: just testing, might not work
  - `🪴 sprout`: has seen some use, might still have hardcoded assumptions and not generalized
  - `🌳 oak`: battle tested. good for general usage
- If a CLI is renamed or removed, update or remove its root `README.md` entry,
  project README, and any compatibility symlink in the same change.
