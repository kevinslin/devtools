# jsonlint

<div align="center"><img src="../../assets/jsonlint-logo.png" alt="JSON validator mascot" width="120" /></div>

`jsonlint` validates JSON content from a file path or stdin.

## Quickstart

```sh
jsonlint path/to/file.json
```

## Command

```sh
jsonlint <path|-> [--quiet]
```

## Arguments

- `path`: JSON file path, or `-` to read from stdin.

## Options

- `--quiet`: suppress success output (`OK`) when JSON is valid.

## Examples

```sh
# validate a file
jsonlint ./payload.json

# validate stdin
cat ./payload.json | jsonlint -
```

## Exit codes

- `0`: valid JSON
- `1`: invalid JSON
- `2`: input read failure
