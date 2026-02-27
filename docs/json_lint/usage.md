# json_lint.py

`json_lint.py` validates JSON content from a file path or stdin.

## Quickstart

```sh
json_lint.py path/to/file.json
```

## Command

```sh
json_lint.py <path|-> [--quiet]
```

## Arguments

- `path`: JSON file path, or `-` to read from stdin.

## Options

- `--quiet`: suppress success output (`OK`) when JSON is valid.

## Examples

```sh
# validate a file
json_lint.py ./payload.json

# validate stdin
cat ./payload.json | json_lint.py -
```

## Exit codes

- `0`: valid JSON
- `1`: invalid JSON
- `2`: input read failure
