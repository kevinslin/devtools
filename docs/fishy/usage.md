# fishy

<div align="center"><img src="../../assets/fishy-logo.png" alt="Fishy emoji" width="120" /></div>

`fishy` serves a local Mermaid preview from stdin by default.


## Quickstart

```sh
fishy < diagram.mmd
```

## Command

```sh
fishy [path| -] [--host HOST] [--port PORT] [--title TITLE] [--no-open]
```

## Arguments

- `path`: optional Mermaid file path. Omit it or pass `-` to read from stdin.

## Options

- `--host`: bind address for the local HTTP server. Default: `127.0.0.1`.
- `--port`: bind port for the local HTTP server. Default: `0` (ask the OS for a free port).
- `--title`: page title shown in the preview window.
- `--no-open`: start the server without opening a browser automatically.

## Behavior

- `fishy` reads Mermaid text first, then starts a local HTTP server and prints the preview URL.
- If the input is a single fenced Markdown block such as ```` ```mermaid ... ``` ````, `fishy` strips the outer fence automatically.
- The preview fits the full diagram into the viewport on first load and includes `Fit`, `-`, and `+` controls for adjusting zoom afterward.
- Long Mermaid note text gets a hover tooltip in the preview so clipped sequence notes can still be read in full.
- The rendered page is local, but the browser loads Mermaid itself from jsDelivr at runtime.
- Press `Ctrl-C` to stop the server.

## Examples

```sh
# render Mermaid piped from stdin
cat diagram.mmd | fishy

# render a file on a fixed port
fishy ./diagram.mmd --port 8123

# keep the server headless and print the URL only
fishy < diagram.mmd --no-open
```

## Exit codes

- `0`: server started successfully and later exited cleanly.
- `1`: Mermaid input could not be read or the local server could not start.
