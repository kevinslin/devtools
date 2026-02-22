# Tools

Small local CLIs for day-to-day developer workflows.

## CLI index

### `tokemon`

Report token usage from local Codex and Claude session logs.

- Entry point: `bin/tokemon`
- Detailed usage: [`docs/specs/tokemon/README.md`](docs/specs/tokemon/README.md)

### `json_lint.py`

Validate JSON from a file or stdin.

- Entry point: `bin/json_lint.py`
- Examples:

```sh
bin/json_lint.py path/to/file.json
cat file.json | bin/json_lint.py -
```
