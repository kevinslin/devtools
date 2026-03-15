# Devtools

A bunch of usefull tools. Designed by human. Made by codex. 

## CLI index

- [agent-sync](docs/agent-sync/usage.md) <img src="assets/agent-sync-inline.png" alt="Agent Sync folders mascot" width="24" height="24" style="vertical-align: text-bottom;" />: Bidirectionally sync selected agent-config files between a live folder and a git repo with file-level conflict detection and dry-run preview
- [arbor](docs/arbor/usage.md) <img src="assets/arbor-inline.png" alt="Arbor bonsai mascot" width="24" height="24" style="vertical-align: text-bottom;" />: Manage git branches/worktrees with merged cleanup, multi-target removal, branch-to-worktree and worktree-to-main conversion, and force-with-lease pushing
- [autocrop-video](docs/autocrop-video/usage.md) <img src="assets/autocrop-video-inline.png" alt="Autocrop video mascot" width="24" height="24" style="vertical-align: text-bottom;" />: Detect the embedded video frame inside a larger screen recording and optionally crop the file to that box
- [diff](docs/diff/usage.md): entry point `bin/diff`; show a git diff from the current working tree against the most recent commit at or before a relative cutoff, with optional `--name-only`
- [tokemon](docs/tokemon/usage.md) <img src="assets/tokemon-inline.png" alt="Tokemon token mascot" width="24" height="24" style="vertical-align: text-bottom;" />: Report token usage from local Codex and Claude session logs, including the data backend used by the Tokemon menu app
- [tokemon-menuapp](docs/tokemon-menuapp/usage.md) <img src="assets/tokemon-menuapp-inline.png" alt="Tokemon menu app mascot" width="24" height="24" style="vertical-align: text-bottom;" />: Build and launch the native Tokemon macOS menu-bar app
- [json_lint.py](docs/json_lint/usage.md) <img src="assets/json_lint-inline.png" alt="JSON validator mascot" width="24" height="24" style="vertical-align: text-bottom;" />: Validate JSON from a file path or stdin
- [mdpaste](docs/mdpaste/usage.md) <img src="assets/mdpaste-inline.png" alt="Markdown clipboard mascot" width="24" height="24" style="vertical-align: text-bottom;" />: Convert Markdown in the clipboard into rich text for paste targets like Gmail and Google Docs
- [mdpreview](docs/mdpreview/usage.md): entry point `bin/mdpreview`; render Markdown from stdin or a file into a localhost preview page with markdown-it plugins
- [ag-man](docs/ag-man/usage.md) <img src="assets/ag-man-inline.png" alt="AG Man ledger mascot" width="24" height="24" style="vertical-align: text-bottom;" />: List today's `ag-ledger` session starts as JSONL with active/inactive process and tmux status, with optional `--filter key=value` and `--group-by workspace`.
- [convo](docs/convo/usage.md) <img src="assets/convo-inline.png" alt="Conversation search mascot" width="24" height="24" style="vertical-align: text-bottom;" />: Search Codex conversation logs with fast regex matching and optional date-window filtering
- [fishy](docs/fishy/usage.md) <img src="assets/fishy-inline.png" alt="Fishy emoji" width="24" height="24" style="vertical-align: text-bottom;" />: Serve a local Mermaid preview from stdin or a file path; entry point `bin/fishy`


## Docs layout

- `docs/[tool-name]/usage.md`: CLI usage docs
- `docs/[tool-name]/spec.md`: tool design/architecture spec
