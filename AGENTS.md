# AGENTS

Repository instructions for agents working in `/Users/kevinlin/code/tools`.

## CLI documentation requirement

For every CLI in this project, keep `README.md` updated.

- Any new CLI added under `bin/` must be added to the `## CLI index` section in `README.md`.
- Use a single-line bullet per CLI (do not create per-tool markdown sections).
- Keep the `## Tool maturity` section in `README.md` present and current.
- Each line must include:
  - Maturity emoji and classification
  - CLI name
  - Entry point path (for example, `bin/<tool>`)
  - One-line description of what the CLI does
  - Link to detailed docs if they exist
- Use exactly one maturity marker per CLI entry:
  - `🌱 seed`: just testing, might not work
  - `🪴 sprout`: has seen some use, might still have hardcoded assumptions and not generalized
  - `🌳 oak`: battle tested. good for general usage
- If a CLI is renamed or removed, update or remove its `README.md` entry in the same change. Similarly, also update its usage docs
