# mdpreview

`mdpreview` renders Markdown from stdin or a file into a local browser preview served from `localhost`.

## Quickstart

```sh
mdpreview < README.md
```

## Command

```sh
mdpreview [path| -] [--host HOST] [--port PORT] [--title TITLE] [--no-open]
```

## Arguments

- `path`: optional Markdown file path. Omit it or pass `-` to read from stdin.

## Options

- `--host`: bind address for the local HTTP server. Default: `127.0.0.1`.
- `--port`: bind port for the local HTTP server. Default: `0` (ask the OS for a free port).
- `--title`: page title shown in the preview window. When a file path is passed and `--title` is omitted, the file name is used.
- `--no-open`: start the server without opening a browser automatically.

## Behavior

- `mdpreview` reads Markdown first, then starts a local HTTP server and prints the preview URL.
- It renders the page with `markdown-it-py`.
- It uses markdown-it plugins for heading anchors, task list checkboxes, and external-link attributes.
- The source Markdown is available at `/source.md` from the local server.
- Press `Ctrl-C` to stop the server.

## Requirements

- `python3`
- `markdown-it-py`

## Examples

```sh
# preview stdin
cat notes.md | mdpreview

# preview a file on a fixed port without auto-opening a browser
mdpreview ./notes.md --port 8123 --no-open
```

## Exit codes

- `0`: server started successfully and later exited cleanly.
- `1`: Markdown input could not be read, rendering failed, or the local server could not start.
