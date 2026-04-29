# epoch

`epoch` converts an epoch timestamp into UTC time, local time, and a relative time.

## Quickstart

```sh
epoch 1777241775789.2769
```

## Command

```sh
epoch TIMESTAMP
```

## Input

- `TIMESTAMP`: epoch time in seconds or milliseconds. Decimal values are accepted.
- Values with an absolute magnitude of `100000000000` or greater are interpreted as milliseconds; smaller values are interpreted as seconds.

## Output

- `UTC`: timestamp formatted in UTC.
- `Local`: timestamp formatted in the machine's local timezone, including the GMT offset and `DST` when daylight saving time is active.
- `Relative`: timestamp relative to the current time.

## Examples

```sh
$ epoch 1777241775789.2769
UTC: Sunday, April 26, 2026 at 10:16:15.789 PM
Local: Sunday, April 26, 2026 at 3:16:15.789 PM GMT-07:00 DST
Relative: 9 minutes ago

$ epoch 1777241775.789
UTC: Sunday, April 26, 2026 at 10:16:15.789 PM
Local: Sunday, April 26, 2026 at 3:16:15.789 PM GMT-07:00 DST
Relative: 9 minutes ago
```

## Exit codes

- `0`: timestamp converted successfully
- `1`: timestamp was invalid or out of range
