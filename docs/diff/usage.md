# diff

`diff` shows the current working tree diff against the most recent commit at or before a relative cutoff. By default it uses the last 24 hours.

## Quickstart

```sh
diff
```

## Command

```sh
diff [window] [--name-only]
```

## Arguments

- `window`: optional relative time window in hours, days, or weeks. Examples: `7h`, `3d`, `1w`. Defaults to `24h`.

## Options

- `--name-only`: print changed file names only. Each path is listed once.

## How It Works

`diff` finds the newest commit on `HEAD` whose commit timestamp is at or before the cutoff, then runs `git diff` from that commit to the current working tree.

This means:

- recent commits are included
- current tracked working tree changes are included
- output is a net diff since the cutoff, not a per-commit patch log

## Examples

```sh
# diff since the last 24 hours
diff

# diff since the last week
diff 1w

# list changed files from the last 7 hours
diff 7h --name-only

# diff since the last 3 days
diff 3d
```
