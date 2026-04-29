# slack-post

`slack-post` posts a plain-text message to a Slack channel through `chat.postMessage`.

## Quickstart

```sh
slack-post --channel C123456789 --token "$SLACK_TOKEN" "hello from devtools"
```

## Command

```sh
slack-post --channel CHANNEL [--token TOKEN] [--thread-ts TS] [--timeout SECONDS] [message...]
```

## Input

- `--channel CHANNEL`: Slack channel ID or name to post into.
- `message`: message text. If omitted, `slack-post` reads the message from stdin.
- `--token TOKEN`: Slack bot or user token. If omitted, `slack-post` uses `SLACK_TOKEN` or `SLACK_BOT_TOKEN`.

## Options

- `--thread-ts TS`: reply in an existing Slack thread.
- `--timeout SECONDS`: request timeout in seconds. Default: `15`.

## Examples

```sh
# pass the message as arguments
slack-post -c C123456789 -t "$SLACK_TOKEN" "deploy finished"

# read the token from the environment
SLACK_TOKEN=xoxb-... slack-post -c C123456789 "deploy finished"

# read a multi-line message from stdin
printf 'line one\nline two\n' | slack-post -c C123456789 -t "$SLACK_TOKEN"

# reply in a thread
slack-post -c C123456789 --thread-ts 1712345678.123456 "follow-up"
```

## Exit codes

- `0`: message posted successfully
- `1`: invalid input, network failure, or Slack API error
