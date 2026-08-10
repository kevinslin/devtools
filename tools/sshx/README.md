# sshx

<div align="center"><img src="../../assets/sshx-logo.png" alt="SSH sync terminal mascot" width="120" /></div>

`sshx` syncs a conservative set of local dotfiles and Codex CLI config files to a remote host with `rsync`, then opens `ssh`. If the remote host does not have `rsync`, the default `auto` mode falls back to a staged `tar` stream over SSH. The staged overlay replaces file, directory, and symlink type conflicts inside selected paths while preserving unrelated remote-only entries.

## Quickstart

```sh
sshx devbox
```

## Command

```sh
sshx [--profile NAME] [--sync-method auto|rsync|tar] [-i PATH] [-o KEY=VALUE] [-p PORT] [--path RELATIVE_PATH ...] [--no-defaults] [--dry-run] host [remote-command...]
```

## Profiles

`sshx` reads profile path lists from `~/.config/sshx/config.yaml` and uses the
`default` profile unless you pass `--profile`. If `XDG_CONFIG_HOME` is set, the
configuration lives at `$XDG_CONFIG_HOME/sshx/config.yaml` instead. The agents
workspace manages and syncs this external configuration through its standalone
chezmoi source.

- `default`: syncs the paths listed under `profiles.default`.
- `work`: syncs the paths listed under `profiles.work`; currently this is the default profile minus `.zshrc`.

For tests or local experiments, set `SSHX_CONFIG_PATH=/path/to/config.yaml` to
load a different config file. This explicit override takes precedence over
`XDG_CONFIG_HOME`.

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
- `.zshrc`
- `.gitconfig`
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
- `.gitconfig`
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
- `--profile NAME`: select a sync profile from `~/.config/sshx/config.yaml`. Available managed profiles: `default`, `work`.
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

# sync the work profile, which omits .zshrc
sshx --profile work devbox

# force tar-over-ssh sync for hosts without remote rsync
sshx --sync-method tar devbox

# sync an extra config directory before opening the session
sshx --path .config/ghostty devbox

# sync only the files you name, then run a remote command
sshx --no-defaults --path .zshrc --path .config/nvim devbox uname -a

# preview the exact commands without running them
sshx -i ~/.ssh/work_ed25519 --dry-run devbox
```
