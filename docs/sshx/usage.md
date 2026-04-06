# sshx

<div align="center"><img src="../../assets/sshx-logo.png" alt="SSH sync terminal mascot" width="120" /></div>

`sshx` syncs a conservative set of local dotfiles to a remote host with `rsync`, then opens `ssh`.

## Quickstart

```sh
sshx devbox
```

## Command

```sh
sshx [-i PATH] [-o KEY=VALUE] [-p PORT] [--path RELATIVE_PATH ...] [--no-defaults] [--dry-run] host [remote-command...]
```

## Default Sync Set

By default, `sshx` syncs the dotfiles and config directories below if they exist under your local home directory:

- `.bashrc`
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

It intentionally skips secret-heavy paths like `.ssh` and auth-oriented config directories.

## Options

- `-i, --identity-file PATH`: pass an SSH identity file to both `rsync` and `ssh`.
- `-o, --option KEY=VALUE`: pass an SSH `-o` option to both `rsync` and `ssh`.
- `-p, --port PORT`: pass a custom SSH port to both `rsync` and `ssh`.
- `--path RELATIVE_PATH`: add another home-relative file or directory to sync.
- `--no-defaults`: sync only the paths you provide with `--path`.
- `--dry-run`: print the `rsync` and `ssh` commands without executing them.

## Examples

```sh
# sync the default dotfiles, then open a shell
sshx devbox

# use a custom SSH key for both rsync and ssh
sshx -i ~/.ssh/work_ed25519 devbox

# sync an extra config directory before opening the session
sshx --path .config/ghostty devbox

# sync only the files you name, then run a remote command
sshx --no-defaults --path .zshrc --path .config/nvim devbox uname -a

# preview the exact commands without running them
sshx -i ~/.ssh/work_ed25519 --dry-run devbox
```
