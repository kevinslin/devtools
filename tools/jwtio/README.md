# jwtio

`jwtio` reads a JWT from stdin and prints the decoded header and payload as pretty JSON, along with the raw signature segment.

## Quickstart

```sh
pbpaste | jwtio
```

## Command

```sh
jwtio [-]
```

## Input

- `stdin`: a single JWT token. `jwtio` also accepts an optional leading `Bearer` prefix and ignores surrounding whitespace.
- `-`: optional conventional stdin marker. `jwtio` reads from stdin with or without it.

## Behavior

- `jwtio` expects a standard 3-segment JWT (`header.payload.signature`).
- It base64url-decodes the header and payload and parses both as JSON.
- Output is a single JSON object with `header`, `payload`, and `signature` keys.
- `jwtio` decodes tokens only; it does not verify the signature.

## Examples

```sh
# decode whatever is in your clipboard
pbpaste | jwtio

# decode with an explicit stdin marker
pbpaste | jwtio -

# decode a token stored in a shell variable
printf '%s\n' "$JWT" | jwtio

# decode an Authorization header value
printf 'Bearer %s\n' "$JWT" | jwtio
```

## Exit codes

- `0`: decoded successfully
- `1`: input was missing or the JWT could not be decoded
