# Devtools

## Tool maturity
| Maturity | Classification | Meaning |
| --- | --- | --- |
| 🌱 | `seed` | just testing, might not work |
| 🪴 | `sprout` | has seen some use, might still have hardcoded assumptions and not generalized |
| 🌳 | `oak` | battle tested. good for general usage |

A bunch of useful tools. Designed by human. Made by codex.

## CLI index

- 🌳 `oak`: [tokemon](docs/tokemon/usage.md) <img src="assets/tokemon-inline.png" alt="Tokemon token mascot" width="24" height="24" style="vertical-align: text-bottom;" />; entry point `bin/tokemon`; report token usage from local Codex and Claude session logs, including the data backend used by the Tokemon menu app
- 🌳 `oak`: [jsonlint](docs/jsonlint/usage.md) <img src="assets/jsonlint-inline.png" alt="JSON validator mascot" width="24" height="24" style="vertical-align: text-bottom;" />; entry point `bin/jsonlint`; validate JSON from a file path or stdin
- 🌳 `oak`: [mdpaste](docs/mdpaste/usage.md) <img src="assets/mdpaste-inline.png" alt="Markdown clipboard mascot" width="24" height="24" style="vertical-align: text-bottom;" />; entry point `bin/mdpaste`; convert Markdown in the clipboard into rich text for paste targets like Gmail and Google Docs
- 🌳 `oak`: [mdpreview](docs/mdpreview/usage.md) <img src="assets/mdpreview-inline.png" alt="Markdown preview mascot" width="24" height="24" style="vertical-align: text-bottom;" />; entry point `bin/mdpreview`; render Markdown from stdin or a file into a localhost preview page with markdown-it plugins
- 🌳 `oak`: [fishy](docs/fishy/usage.md) <img src="assets/fishy-inline.png" alt="Fishy emoji" width="24" height="24" style="vertical-align: text-bottom;" />; entry point `bin/fishy`; serve a local Mermaid preview from stdin or a file path
- 🪴 `sprout`: [arbor](docs/arbor/usage.md) <img src="assets/arbor-inline.png" alt="Arbor bonsai mascot" width="24" height="24" style="vertical-align: text-bottom;" />; entry point `bin/arbor`; manage git branches/worktrees with merged cleanup, multi-target removal, branch-to-worktree and worktree-to-main conversion, and force-with-lease pushing
- 🪴 `sprout`: [diff](docs/diff/usage.md) <img src="assets/diff-inline.png" alt="Diff patch mascot" width="24" height="24" style="vertical-align: text-bottom;" />; entry point `bin/diff`; show a git diff from the current working tree against the most recent commit at or before a relative cutoff, with optional `--name-only`
- 🪴 `sprout`: [tokemon-menuapp](docs/tokemon-menuapp/usage.md) <img src="assets/tokemon-menuapp-inline.png" alt="Tokemon menu app mascot" width="24" height="24" style="vertical-align: text-bottom;" />; entry point `bin/tokemon-menuapp`; build and launch the native Tokemon macOS menu-bar app
- 🌱 `seed`: [agent-sync](docs/agent-sync/usage.md) <img src="assets/agent-sync-inline.png" alt="Agent Sync folders mascot" width="24" height="24" style="vertical-align: text-bottom;" />; entry point `bin/agent-sync`; bidirectionally sync selected agent-config files between a live folder and a git repo with file-level conflict detection and dry-run preview
- 🌱 `seed`: [autocrop-video](docs/autocrop-video/usage.md) <img src="assets/autocrop-video-inline.png" alt="Autocrop video mascot" width="24" height="24" style="vertical-align: text-bottom;" />; entry point `bin/autocrop-video`; detect the embedded video frame inside a larger screen recording and optionally crop the file to that box
- 🌱 `seed`: [convo](docs/convo/usage.md) <img src="assets/convo-inline.png" alt="Conversation search mascot" width="24" height="24" style="vertical-align: text-bottom;" />; entry point `bin/convo`; search Codex conversation logs with fast regex matching and optional date-window filtering
- 🌱 `seed`: [jwtio](docs/jwtio/usage.md); entry point `bin/jwtio`; decode a JWT from stdin into pretty JSON showing the header, payload, and signature fields
- 🌱 `seed`: [sshx](docs/sshx/usage.md) <img src="assets/sshx-inline.png" alt="SSH sync terminal mascot" width="24" height="24" style="vertical-align: text-bottom;" />; entry point `bin/sshx`; sync a conservative set of local dotfiles plus Codex CLI config, agents, hooks, rules, and skills to a remote host with rsync, then open ssh with optional identity and SSH options

## Docs layout

- `docs/[tool-name]/usage.md`: CLI usage docs
- `docs/[tool-name]/spec.md`: tool design/architecture spec
