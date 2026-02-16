#!/usr/bin/env python3
"""Local JSON lint tool.

Usage:
  json_lint.py path/to/file.json
  cat file.json | json_lint.py -
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def _format_error(text: str, line: int, col: int) -> str:
    lines = text.splitlines()
    if 1 <= line <= len(lines):
        error_line = lines[line - 1]
        caret = " " * (max(col - 1, 0)) + "^"
        return f"Line {line}, Column {col}:\n{error_line}\n{caret}"
    return f"Line {line}, Column {col}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint JSON files or stdin.")
    parser.add_argument("path", help="JSON file path or '-' for stdin")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress success output",
    )
    args = parser.parse_args()

    try:
        content = _read_input(args.path)
    except OSError as exc:
        print(f"error: failed to read input: {exc}", file=sys.stderr)
        return 2

    try:
        json.loads(content)
    except json.JSONDecodeError as exc:
        print("error: invalid JSON", file=sys.stderr)
        print(_format_error(content, exc.lineno, exc.colno), file=sys.stderr)
        if exc.msg:
            print(f"Reason: {exc.msg}", file=sys.stderr)
        return 1

    if not args.quiet:
        print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
