# Devtools

A bunch of usefull tools. Designed by human. Made by codex. 

## CLI index

- `agent-sync` (`bin/agent-sync`): Bidirectionally sync selected agent-config files between a live folder and a git repo with file-level conflict detection and dry-run preview; detailed usage in [`docs/agent-sync/usage.md`](docs/agent-sync/usage.md).
- [arbor](docs/arbor/usage.md) <img src="docs/assets/arbor-inline.png" alt="Arbor bonsai mascot" width="24" style="vertical-align: text-bottom;" />: Manage git branches/worktrees with merged cleanup, multi-target removal, branch-to-worktree and worktree-to-main conversion, and force-with-lease pushing
- `autocrop-video` (`bin/autocrop-video`): Detect the embedded video frame inside a larger screen recording and optionally crop the file to that box; detailed usage in [`docs/autocrop-video/usage.md`](docs/autocrop-video/usage.md).
- `tokemon` (`bin/tokemon`): Report token usage from local Codex and Claude session logs, including the data backend used by the Tokemon menu app; detailed usage in [`docs/tokemon/usage.md`](docs/tokemon/usage.md).
- `tokemon-menuapp` (`bin/tokemon-menuapp`): Build and launch the native Tokemon macOS menu-bar app; detailed usage in [`docs/tokemon-menuapp/usage.md`](docs/tokemon-menuapp/usage.md).
- `json_lint.py` (`bin/json_lint.py`): Validate JSON from a file path or stdin; detailed usage in [`docs/json_lint/usage.md`](docs/json_lint/usage.md).
- `mdpaste` (`bin/mdpaste`): Convert Markdown in the clipboard into rich text for paste targets like Gmail and Google Docs; detailed usage in [`docs/mdpaste/usage.md`](docs/mdpaste/usage.md).
- `ag-man` (`bin/ag-man`): List today's `ag-ledger` session starts as JSONL with active/inactive process and tmux status, with optional `--filter key=value` and `--group-by workspace`.
- `convo` (`bin/convo`): Search Codex conversation logs with fast regex matching and optional date-window filtering; detailed usage in [`docs/convo/usage.md`](docs/convo/usage.md).
- [fishy](docs/fishy/usage.md) <img src="docs/assets/fishy-inline.png" alt="Fishy emoji" width="24" style="vertical-align: text-bottom;" />: Serve a local Mermaid preview from stdin or a file path; entry point `bin/fishy`


## Docs layout

- `docs/[tool-name]/usage.md`: CLI usage docs
- `docs/[tool-name]/spec.md`: tool design/architecture spec
