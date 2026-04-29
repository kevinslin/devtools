# fishy

<div align="center"><img src="../../assets/fishy-logo.png" alt="Fishy emoji" width="120" /></div>

`fishy` serves a local Mermaid preview from stdin by default. It can also extract Mermaid blocks from a Markdown source file.


## Quickstart

```sh
fishy < diagram.mmd
fishy --source-file flow.md
```

## Command

```sh
fishy [path| -] [--source-file FILE] [--host HOST] [--port PORT] [--title TITLE] [--no-open]
```

## Arguments

- `path`: optional Mermaid file path. Omit it or pass `-` to read from stdin.

## Options

- `--source-file`: read a Markdown source file, extract all `mermaid` fenced code blocks, and refresh the preview when the file changes. Cannot be combined with `path`.
- `--host`: bind address for the local HTTP server. Default: `127.0.0.1`.
- `--port`: bind port for the local HTTP server. Default: `0` (ask the OS for a free port).
- `--title`: page title shown in the preview window.
- `--no-open`: start the server without opening a browser automatically.

## Behavior

- `fishy` reads Mermaid text first, then starts a local HTTP server and prints the preview URL.
- If the input is a single fenced Markdown block such as ```` ```mermaid ... ``` ````, `fishy` strips the outer fence automatically.
- With `--source-file`, `fishy` parses the Markdown file for all fenced `mermaid` code blocks and renders each as a separate preview block.
- Source-file preview titles come from the nearest preceding Markdown heading. Blocks before any heading are titled `Mermaid block N`.
- Source-file previews poll the source file and reload the browser page when its mtime or size changes.
- The preview spans the page width and fits the diagram to that width on first load.
- Drag inside the preview to pan. Double-click to zoom in at the pointer; `Shift`/`Option` double-click zooms out.
- The toolbar includes `Fit width`, `-`, and `+` controls for adjusting zoom afterward.
- Long Mermaid note text gets a hover tooltip in the preview so clipped sequence notes can still be read in full.
- The rendered page is local, but the browser loads Mermaid itself from jsDelivr at runtime.
- Press `Ctrl-C` to stop the server.

## Examples

```sh
# render Mermaid piped from stdin
cat diagram.mmd | fishy

# render a file on a fixed port
fishy ./diagram.mmd --port 8123

# render all Mermaid blocks from a Markdown file and refresh on edits
fishy --source-file ./flow.md

# keep the server headless and print the URL only
fishy < diagram.mmd --no-open
```

## Exit codes

- `0`: server started successfully and later exited cleanly.
- `1`: Mermaid input could not be read or the local server could not start.
