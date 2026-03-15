---
name: tool-icons
description: Create and wire tool-specific icons into a project's docs. Use when the user asks to generate or refresh an icon for a particular CLI or tool, link the tool name in README.md to its usage doc, add an inline icon beside the linked name, and add a centered logo block under the H1 title in the tool usage doc.
dependencies:
- icon-gen
---

# tool-icons

Generate a tool icon with `icon-gen`, save the assets under the repo-root `assets/` directory, then update both the root README and the tool usage doc to reference those assets in the repo's standard format.

## Workflow

1. Collect the tool inputs:
   - tool name, for example `fishy`
   - subject or mascot prompt for the icon
   - optional style; default to `chibi`
   - short alt text for the logo
2. Set paths:
   - `ROOT_DIR=$(pwd)`
   - `ASSETS_DIR="$ROOT_DIR/assets"`
   - `README_PATH="$ROOT_DIR/README.md"`
   - `USAGE_PATH="$ROOT_DIR/docs/<tool>/usage.md"`
3. Use the `icon-gen` dependency to create both assets for the tool:
   - general icon path: `assets/<tool>-logo.png`
   - inline icon path: `assets/<tool>-inline.png`
4. Update docs with `scripts/update_tool_docs.py`:
   - downsize `assets/<tool>-logo.png` to a maximum of `240px` on its longest side
   - rewrite the README bullet so the linked CLI name comes first, with no parenthesized path after the name
   - place the inline icon immediately after the linked CLI name using a normalized high-resolution PNG so bottoms stay aligned in the README
   - add the centered logo block immediately after the `#` title in `docs/<tool>/usage.md`
5. Verify both files:
   - the logo asset should be at most `240px` on its longest side
   - the README bullet should render the inline icon beside the tool name
   - the usage doc should contain exactly:

```html
<div align="center"><img src="../../assets/<tool>-logo.png" alt="<alt description>" width="120" /></div>
```

## Output contract

- Write assets to repo-root `assets/`.
- Use these filenames:
  - `assets/<tool>-logo.png`
  - `assets/<tool>-inline.png`
- Keep `assets/<tool>-logo.png` at a maximum of `240px` on its longest side.
- Normalize README inline icons to `256x256` PNG assets and render them at `24x24` with `vertical-align: text-bottom`.
- Trim transparent padding, then pad back to the square canvas against the bottom edge so baseline alignment is consistent.
- Keep the usage-doc logo block directly under the H1.
- Keep the README bullet single-line.
- Link the CLI name to its usage doc, for example `[fishy](docs/fishy/usage.md)`.
- Do not add a trailing `detailed usage in ...` clause to the README bullet.
- Preserve the existing description text in the README bullet after the colon, except for removing any old trailing detailed-usage clause.

## Commands

- Doc wiring helper: `python3 .agents/skills/tool-icons/scripts/update_tool_docs.py --tool <tool> --readme README.md --usage docs/<tool>/usage.md --inline-src assets/<tool>-inline.png --logo-src ../../assets/<tool>-logo.png --alt "<alt description>"`
