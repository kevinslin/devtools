# ag-man

<div align="center"><img src="../assets/ag-man-logo.png" alt="AG Man ledger mascot" width="120" /></div>

`ag-man` lists today's `ag-ledger` session starts and reports whether each session still has an active process.

## Quickstart

```sh
ag-man
```

## Command

```sh
ag-man [--filter key=value] [--group-by workspace]
```

## Options

- `--filter key=value`: keep only rows whose JSON output field matches the given value.
- `--group-by workspace`: group the output by workspace instead of printing a flat list.

## Output

`ag-man` prints JSONL describing sessions started today, including the session id, workspace, process liveness, and tmux status when available.

## Examples

```sh
# show all sessions started today
ag-man

# show only sessions for one workspace
ag-man --filter workspace=/Users/kevinlin/code/tools

# group today's sessions by workspace
ag-man --group-by workspace
```
