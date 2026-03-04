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
