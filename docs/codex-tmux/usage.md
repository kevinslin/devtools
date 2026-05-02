# codex-tmux

`codex-tmux` inventories tmux panes that have a Codex process running under the pane process tree.

## Quickstart

```sh
codex-tmux
```

## Command

```sh
codex-tmux [--all] [--format table|json] [--capture-lines N] [--no-capture]
```

## What It Reports

- tmux location as `session:window.pane`
- numeric tmux pane display id, active-pane flag, current command, and current path
- detected Codex process pid and command
- visible state inferred from recent pane text and process-tree evidence

## State Labels

- `needs-approval`: recent pane text looks like Codex is asking for confirmation or permission
- `running-tool`: the Codex process currently has non-helper child processes, usually from a running shell command or tool call
- `working`: recent pane text contains a visible busy status
- `idle`: recent pane text contains a visible prompt or ready status
- `unknown`: Codex is present, but no recognizable state evidence was visible
- `not-codex`: only emitted with `--all`

The state is evidence-based. It uses `tmux capture-pane` and `ps`; it does not read private Codex runtime internals.

## Options

- `--all`: include panes without a Codex process
- `--format table`: print a compact human-readable table; this is the default
- `--format json`: print scriptable JSON
- `--capture-lines N`: inspect the last `N` pane lines for visible state; defaults to `80`
- `--no-capture`: skip pane capture and report only process-tree state

## Examples

```sh
$ codex-tmux
LOCATION      PANE  WINDOW  ACTIVE  STATE         CODEX_PID  CWD        EVIDENCE
------------  ----  ------  ------  ------------  ---------  ---------  -------------------------------
0:1.0         5     work    yes     running-tool  12345      /repo/app  child processes: zsh(12360)

$ codex-tmux --format json
{
  "codex_pane_count": 1,
  "generated_at": "2026-04-29T18:00:00.000000Z",
  "pane_count": 4,
  "panes": [
    {
      "location": "0:1.0",
      "pane_id": "%5",
      "pane_display_id": "5",
      "codex": true,
      "state": "running-tool"
    }
  ]
}
```

## Exit Codes

- `0`: inventory collected successfully
- `1`: tmux or process inventory could not be collected
