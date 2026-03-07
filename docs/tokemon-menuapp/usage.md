# Tokemon Menu App

`tokemon-menuapp` builds a native macOS menu-bar app for Tokemon and, by default, opens it after the bundle is written.

## Quickstart

```sh
bin/tokemon-menuapp
```

By default this installs the app bundle at `~/Applications/Tokemon.app` and opens it.

## Command

```sh
tokemon-menuapp [--output PATH] [--no-open]
```

## Options

- `--output PATH`: write the app bundle to a specific path instead of `~/Applications/Tokemon.app`
- `--no-open`: build the app bundle without launching it

## UI behavior

Clicking the Tokemon menu-bar icon toggles a chart window with:

- `Today`: hourly token totals for the current local day
- `Week`: daily token totals for the last 7 calendar days
- `Month`: weekly token totals for roughly the trailing calendar month
- `Year`: monthly token totals for the last 12 calendar months

The menu app reads from the bundled `tokemon` CLI and combines Codex plus Claude usage (`--provider all`).
The window stays open when focus moves elsewhere and closes only when you click the menu-bar icon again or quit the app.
Recent snapshots are cached on disk, so reopening the app or toggling ranges shows the last fetched chart immediately while a background refresh updates it.
The underlying CLI also keeps a persistent Codex index, so repeated refreshes usually reuse unchanged session logs. Set `TOKEMON_INDEX_PATH` or `TOKEMON_DISABLE_INDEX=1` before launching the app if you need to relocate or bypass that index.
