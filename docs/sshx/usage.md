# sshx

<div align="center"><img src="../../assets/sshx-logo.png" alt="SSH sync terminal mascot" width="120" /></div>

`sshx` syncs a conservative set of local dotfiles and Codex CLI config files to a remote host with `rsync`, then opens `ssh`. If the remote host does not have `rsync`, the default `auto` mode falls back to a `tar` stream over SSH. It preserves the remote `.zshrc` and installs a reviewed, credential-free overlay as `.zshrc.local`.

## Quickstart

```sh
sshx devbox
```

## Command

```sh
sshx [--profile NAME] [--sync-method auto|rsync|tar] [-i PATH] [-o KEY=VALUE] [-p PORT] [--path RELATIVE_PATH ...] [--no-defaults] [--dry-run] host [remote-command...]
```

## Profiles

`sshx` reads profile path lists from `config/sshx/config.yaml` and uses the `default` profile unless you pass `--profile`.

- `default`: syncs the paths and shell overlay listed under `profiles.default`.
- `work`: currently matches `default`; the separate name remains available for profile-specific divergence without reintroducing direct `.zshrc` replacement.

Neither bundled profile syncs the home-level `.gitconfig`. Put portable Git configuration under `.config/git`, which both profiles continue to sync.

For tests or local experiments, set `SSHX_CONFIG_PATH=/path/to/config.yaml` to load a different config file and `SSHX_ZSH_OVERLAY_PATH=/path/to/zshrc` to test another reviewed overlay.

### Zsh overlay

The reserved `@zsh-overlay` profile entry merges `config/sshx/zshrc.remote.local` into a marked block in remote `~/.zshrc.local`, which is kept at mode `0600`. Content outside the managed block is preserved. Direct `.zshrc` sync is rejected, including through `--path`. The installer normalizes this source block exactly once at the end of the remote `~/.zshrc`:

```zsh
# >>> sshx zshrc.local >>>
[[ -r "$HOME/.zshrc.local" ]] && source "$HOME/.zshrc.local"
# <<< sshx zshrc.local <<<
```

Before changing either file for the first time, `sshx` preserves mode-`0600` copies as `~/.zshrc.sshx-base` and `~/.zshrc.local.sshx-base`. Existing unmarked `.zshrc.local` content survives alongside this managed section. Malformed managed markers and symlinked rc files are rejected instead of rewritten.

```zsh
# >>> sshx managed overlay >>>
# contents of config/sshx/zshrc.remote.local
# <<< sshx managed overlay <<<
```

The overlay receives a conservative review guard before upload. Common direct assignments to credential-like variables, `HOME`, `PNPM_HOME`, or `SSH_AUTH_SOCK`, and Mac-only absolute paths are rejected; this is not a shell-language security sandbox. Edit `config/sshx/zshrc.remote.local` when adding portable aliases or functions and review the diff; do not copy a personal `.zshrc.local` into it wholesale.

## Default Profile

The `default` profile syncs the dotfiles and config directories below if they exist under your local home directory:

- `.bashrc`
- `.codex/agents`
- `.codex/config.toml`
- `.codex/hooks`
- `.codex/hooks.json`
- `.codex/rules`
- `.codex/skills`
- `.profile`
- `.zlogin`
- `.zprofile`
- `.zshenv`
- `@zsh-overlay` (installs `config/sshx/zshrc.remote.local` as remote `.zshrc.local`)
- `.git.scmbrc`
- `.scmbrc`
- `.tmux.conf`
- `.vimrc`
- `.config/fish`
- `.config/git`
- `.config/iterm2`
- `.config/nvim`
- `.config/uv`

## Work Profile

The `work` profile syncs the dotfiles and config directories below if they exist under your local home directory:

- `@zsh-overlay` (installs `config/sshx/zshrc.remote.local` as remote `.zshrc.local`)
- `.bashrc`
- `.codex/agents`
- `.codex/config.toml`
- `.codex/hooks`
- `.codex/hooks.json`
- `.codex/rules`
- `.codex/skills`
- `.profile`
- `.zlogin`
- `.zprofile`
- `.zshenv`
- `.git.scmbrc`
- `.scmbrc`
- `.tmux.conf`
- `.vimrc`
- `.config/fish`
- `.config/git`
- `.config/iterm2`
- `.config/nvim`
- `.config/uv`

It intentionally skips secret-heavy paths like `.ssh`, Codex auth state such as `auth.json`, and other auth-oriented config directories.

## Options

- `-i, --identity-file PATH`: pass an SSH identity file to both `rsync` and `ssh`.
- `-o, --option KEY=VALUE`: pass an SSH `-o` option to both `rsync` and `ssh`.
- `-p, --port PORT`: pass a custom SSH port to both `rsync` and `ssh`.
- `--profile NAME`: select a sync profile from `config/sshx/config.yaml`. Available bundled profiles: `default`, `work`.
- `--sync-method auto|rsync|tar`: choose the sync transport. `auto` checks whether the remote has `rsync`, uses it when available, and falls back to `tar` over SSH when it is missing.
- `--path RELATIVE_PATH`: add another home-relative file or directory to sync.
- `--no-defaults`: sync only the paths you provide with `--path`.
- `--dry-run`: print the sync and `ssh` commands without executing them.

If the `rsync` transport drops with SSH exit code `255`, `sshx` retries the sync once before giving up.

## Examples

```sh
# sync the default dotfiles, then open a shell
sshx devbox

# use a custom SSH key for both rsync and ssh
sshx -i ~/.ssh/work_ed25519 devbox

# sync the work profile with the safe zsh overlay
sshx --profile work devbox

# force tar-over-ssh sync for hosts without remote rsync
sshx --sync-method tar devbox

# sync an extra config directory before opening the session
sshx --path .config/ghostty devbox

# sync only the files you name, then run a remote command
sshx --no-defaults --path .tmux.conf --path .config/nvim devbox uname -a

# preview the exact commands without running them
sshx -i ~/.ssh/work_ed25519 --dry-run devbox
```
