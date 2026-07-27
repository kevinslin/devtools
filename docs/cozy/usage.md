# Cozy

Cozy is a small, standard-library-only Go CLI for running local development
services behind clean `http://<name>.localhost` URLs. Its embedded reverse
proxy listens on loopback and selects each service by the HTTP `Host` header.
It does not install, configure, or modify DNS.

## Install

```sh
/Users/kevinlin/code/devtools/bin/cozy --help
```

The executable entry point is `bin/cozy` in the `devtools` repository. It
automatically builds and caches the Go source from `src/cozy`, rebuilds when
that source changes, and loads the repository-managed default configuration.
Add the `devtools/bin` directory to your `PATH` to run the shorter `cozy`
commands below.

## Configure

The default site configuration lives in `config/cozy/config.yaml`:

```yaml
version: 1
sites:
  - name: fishy.localhost
    url: http://fishy.localhost
    run: fishy --host 127.0.0.1 --port "$PORT" --no-open
  - name: agtask.localhost
    url: http://agtask.localhost
    run: /Users/kevinlin/code/devtools/bin/cozy __agtask_dashboard
```

Each site has a unique `.localhost` name, its matching clean `http` URL, and a
command to run. Commands are executed by the local shell. Cozy assigns each
command its own available loopback port and sets both `PORT` and `COZY_PORT`
to that port; the service must listen on the provided port. Fishy's `--port`
argument uses that assigned port, and `--no-open` keeps the background service
from opening its internal backend URL. Treat the site configuration as trusted
local configuration. Set `COZY_CONFIG` or pass `--config` to select a different
configuration file.

The `agtask.localhost` entry starts the dashboard using:

```text
/Users/kevinlin/code/skills-public/active/agtask/skills/agtask/scripts/agtask dashboard --no-open
```

Cozy's internal dashboard adapter preserves the dashboard's private token,
expected backend host, and same-origin request checks while making the
dashboard available through its `.localhost` site.

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

The default proxy listener is `127.0.0.1:80`, which keeps public-facing URLs
free of a port. If that address is already occupied or the operating system
denies access, Cozy reports the listener error; it does not request elevated
privileges or reconfigure the system. Release the conflicting listener or
choose an explicit listener for development or testing:

```sh
cozy check --listen 127.0.0.1:8080
cozy up --listen 127.0.0.1:8080
```

An explicitly selected nondefault listener must be included in requests to the
proxy. Clean port-free URLs require an available port 80 listener. Use
`--config` to select a configuration file and `--state-dir` to select a runtime
directory for supported commands.

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
cd /Users/kevinlin/code/devtools/src/cozy
gofmt -w cmd internal
go vet ./...
go test ./...
```

Tests use temporary directories and automatically allocated loopback ports;
they do not depend on DNS changes, port 80, installed local services, or an
existing Cozy instance.
