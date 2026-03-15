#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import pathlib
import re
import sys


def update_readme(
    readme_path: pathlib.Path,
    tool: str,
    usage_doc: pathlib.Path,
    inline_src: str,
    alt: str,
    width: int,
) -> None:
    lines = readme_path.read_text().splitlines()
    updated = False
    usage_link_path = os.path.relpath(usage_doc, start=readme_path.parent).replace(os.sep, "/")
    bullet_re = re.compile(
        rf'^- (?:(?:`{re.escape(tool)}`(?: \([^)]*\))?)|\[{re.escape(tool)}\]\([^)]+\))(?: <img [^>]+ />)?: (?P<body>.*)$'
    )
    usage_link = f"[{tool}]({usage_link_path})"
    icon_html = (
        f'{usage_link} <img src="{inline_src}" alt="{alt}" width="{width}" '
        'style="vertical-align: text-bottom;" />: '
    )

    for idx, line in enumerate(lines):
        match = bullet_re.match(line)
        if not match:
            continue
        body = re.sub(
            r"; detailed usage in \[[^\]]+\]\([^)]+\)\.?$",
            "",
            match.group("body"),
        ).strip()
        lines[idx] = f"- {icon_html}{body}"
        updated = True
        break

    if not updated:
        raise SystemExit(f"could not find README bullet for tool: {tool}")

    readme_path.write_text("\n".join(lines) + "\n")


def update_usage(usage_path: pathlib.Path, logo_src: str, alt: str, width: int) -> None:
    lines = usage_path.read_text().splitlines()
    if not lines or not lines[0].startswith("# "):
        raise SystemExit(f"usage doc must start with an H1: {usage_path}")

    logo_line = f'<div align="center"><img src="{logo_src}" alt="{alt}" width="{width}" /></div>'

    rest = lines[1:]
    while rest and rest[0] == "":
        rest = rest[1:]

    if rest and re.fullmatch(r'<div align="center"><img src="[^"]+" alt="[^"]+" width="\d+" /></div>', rest[0]):
        rest = rest[1:]
        while rest and rest[0] == "":
            rest = rest[1:]

    updated_lines = [lines[0], "", logo_line, ""]
    updated_lines.extend(rest)
    usage_path.write_text("\n".join(updated_lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool", required=True)
    parser.add_argument("--readme", required=True)
    parser.add_argument("--usage", required=True)
    parser.add_argument("--inline-src", required=True)
    parser.add_argument("--logo-src", required=True)
    parser.add_argument("--alt", required=True)
    parser.add_argument("--inline-width", type=int, default=24)
    parser.add_argument("--logo-width", type=int, default=120)
    args = parser.parse_args()

    readme_path = pathlib.Path(args.readme)
    usage_path = pathlib.Path(args.usage)

    update_readme(
        readme_path,
        args.tool,
        pathlib.Path(args.usage),
        args.inline_src,
        args.alt,
        args.inline_width,
    )
    update_usage(usage_path, args.logo_src, args.alt, args.logo_width)
    return 0


if __name__ == "__main__":
    sys.exit(main())
