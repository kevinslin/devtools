# Devtools

A bunch of usefull tools. Designed by human. Made by codex. 

## CLI index

- `arbor` (`bin/arbor`): Manage git branches/worktrees, including cleanup of fully merged branch worktrees; detailed usage in [`docs/arbor/usage.md`](docs/arbor/usage.md).
- `tokemon` (`bin/tokemon`): Report token usage from local Codex and Claude session logs; detailed usage in [`docs/tokemon/usage.md`](docs/tokemon/usage.md).
- `json_lint.py` (`bin/json_lint.py`): Validate JSON from a file path or stdin; detailed usage in [`docs/json_lint/usage.md`](docs/json_lint/usage.md).
- `ag-man` (`bin/ag-man`): List today's `ag-ledger` session starts as JSONL with active/inactive process and tmux status, with optional `--filter key=value` and `--group-by workspace`.

## Docs layout

- `docs/[tool-name]/usage.md`: CLI usage docs
- `docs/[tool-name]/spec.md`: tool design/architecture spec
