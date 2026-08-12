# Cozy

Cozy is a small, standard-library-only Go CLI for running local development
services behind clean `http://<name>.localhost` URLs. Its embedded reverse
proxy listens on loopback and selects each service by the HTTP `Host` header.
It does not install, configure, or modify DNS. A built-in admin dashboard is
available at `http://cozy.localhost:8080/`.

## Install

```sh
/Users/kevinlin/code/devtools/scripts/install.sh
~/.local/bin/cozy --help
```

The executable entry point is `tools/cozy/bin/cozy` in the `devtools`
repository. The installer symlinks it into `~/.local/bin` by default; set
`INSTALL_BIN_DIR` to choose another installation directory. It automatically
builds and caches the Go source from `tools/cozy/src`, rebuilds when that
source changes, and loads your user-managed default configuration. Add the
installation directory to your `PATH` to run the shorter `cozy` commands
below.

## Configure

The default site configuration lives in `~/.config/cozy/config.yaml`, or
`$XDG_CONFIG_HOME/cozy/config.yaml` when `XDG_CONFIG_HOME` is set. The portable
source of truth is the separate `~/agents` chezmoi configuration; the
`devtools` repository does not own machine-local runtime configuration:

```yaml
version: 1
sites:
  - name: fishy.localhost
    url: http://fishy.localhost
    run: fishy --host 127.0.0.1 --port "$PORT" --no-open
  - name: agtask.localhost
    url: http://agtask.localhost
    redirect_command: agtask dashboard --no-open
```

Each site has a unique `.localhost` name, its matching clean `http` URL, and a
single `run` or `redirect_command` command. Commands are executed by the local
shell. Cozy assigns each `run` command its own available loopback port and sets
both `PORT` and `COZY_PORT` to that port; the service must listen on the
provided port. Fishy's `--port` argument uses that assigned port, and
`--no-open` keeps the background service from opening its internal backend URL.
A `redirect_command` runs once at startup, prints one HTTP or HTTPS URL, and
exits; Cozy redirects that site's requests to the printed URL while preserving
their paths and query strings. Treat the site configuration as trusted local
configuration. Set `COZY_CONFIG` or pass `--config` to select a different
configuration file.

The `cozy.localhost` hostname is reserved for the admin dashboard and cannot
be assigned to a managed service.

The `agtask.localhost` example resolves its configured dashboard using:

```text
agtask dashboard --no-open
```

When agtask uses its Sites backend, the command prints the private hosted Site
URL. Browser authentication and hosted task data remain authoritative, and
Cozy never handles the Site's credentials. Existing `run` configurations,
including the internal agtask dashboard adapter, remain supported.

## Commands

```sh
cozy check
cozy up
cozy status
cozy refresh
cozy restart agtask.localhost
cozy logs fishy.localhost
cozy logs agtask.localhost
cozy open fishy.localhost
cozy open agtask.localhost
cozy down
```

`cozy up` validates the configuration, starts a background supervisor and
reverse proxy, and waits for each service to accept connections on its assigned
loopback port. `cozy down` verifies the supervisor's private control socket
before stopping the supervisor and its managed process groups.
`cozy refresh` rereads the active configuration, adds or removes sites, and
restarts changed services without interrupting unchanged services or the
reverse proxy. Sending `SIGHUP` to the supervisor performs the same refresh.
`cozy restart agtask.localhost` starts a fresh AGTask process while keeping
Fishy and the proxy running; edits to the AGTask Python script are picked up
without rebuilding Cozy. Running `cozy restart` without a site restarts all
managed services while preserving the running supervisor and proxy.
`cozy logs` prints a site's captured output, and `cozy open` opens its clean URL
using the macOS `open` command.

## Admin dashboard

Start Cozy without specifying a port:

```sh
cozy up
```

The predefined listener is `127.0.0.1:8080`. Open
`http://cozy.localhost:8080/` to see every running service, its status, backend
port, process ID, and logs. Restart an individual service from its card or add
a new `.localhost` service using the built-in form. New services are saved to
the active configuration, started immediately, and routed without interrupting
existing sites. Admin mutations are restricted to same-origin local requests.

Use `--listen` to explicitly select another loopback port, `--config` to select
a configuration file, and `--state-dir` to select a runtime directory.

## Start automatically at login

The `~/agents` chezmoi source owns both `~/.config/cozy/config.yaml` and the
macOS user LaunchAgent at `~/Library/LaunchAgents/com.kevinlin.cozy.plist`.
Install or update only these managed targets with:

```sh
chezmoi --source "$HOME/agents" apply \
  "$HOME/.config/cozy" \
  "$HOME/Library/LaunchAgents/com.kevinlin.cozy.plist"
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.kevinlin.cozy.plist"
```

If the agent is already loaded, reload it after applying an updated plist:

```sh
launchctl bootout "gui/$(id -u)/com.kevinlin.cozy"
launchctl bootstrap "gui/$(id -u)" \
  "$HOME/Library/LaunchAgents/com.kevinlin.cozy.plist"
```

The agent starts Cozy at login on `127.0.0.1:8080`, supervises the foreground
Cozy process, and restarts the supervisor automatically if it exits. Fishy,
AGTask, and other configured sites are started together with the admin
dashboard. The agent supplies the Devtools executable path and Go build cache
explicitly because macOS LaunchAgents do not load interactive shell profiles.

Check the running agent and stop automatic restarts with:

```sh
launchctl print "gui/$(id -u)/com.kevinlin.cozy"
launchctl bootout "gui/$(id -u)/com.kevinlin.cozy"
```

Use `launchctl bootout`, not `cozy down`, when stopping a launchd-managed Cozy
for more than a moment: the agent's `KeepAlive` setting restarts the foreground
supervisor after `cozy down`.

## Runtime state

On macOS, the default runtime directory is:

```text
~/Library/Application Support/cozy/
```

Cozy stores supervisor and service metadata, a private authenticated Unix
control socket, supervisor diagnostics, and per-site logs there. Runtime
directories, control sockets, and metadata are created with user-only
permissions. No remote Git repository or system service is required.

The dependency-free configuration reader supports Cozy's documented version 1
mapping and site list, including quoted values and comments. It is deliberately
not a general-purpose YAML processor.

## Development

```sh
cd /Users/kevinlin/code/devtools/tools/cozy/src
gofmt -w cmd internal
go vet ./...
go test ./...
```

Tests use temporary directories and automatically allocated loopback ports;
they do not depend on DNS changes, installed local services, or an existing
Cozy instance.
