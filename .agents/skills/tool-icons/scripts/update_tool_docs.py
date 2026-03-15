#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile


def downsize_logo_asset(usage_path: pathlib.Path, logo_src: str, max_dim: int) -> None:
    logo_path = (usage_path.parent / logo_src).resolve()
    if not logo_path.exists():
        raise SystemExit(f"logo asset not found: {logo_path}")

    if _downsize_with_pillow(logo_path, max_dim):
        return
    if _downsize_with_sips(logo_path, max_dim):
        return

    raise SystemExit("logo downsizing requires Pillow or macOS sips")


def normalize_inline_png(readme_path: pathlib.Path, inline_src: str, target_size: int) -> None:
    inline_path = (readme_path.parent / inline_src).resolve()
    if not inline_path.exists():
        raise SystemExit(f"inline asset not found: {inline_path}")
    if inline_path.suffix.lower() != ".png":
        raise SystemExit(f"inline asset must be a PNG: {inline_path}")
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required to normalize inline icons")

    crop_spec = _detect_crop_spec(inline_path)
    filter_parts = []
    if crop_spec:
        filter_parts.append(f"crop={crop_spec}")
    filter_parts.append(
        f"scale={target_size}:{target_size}:force_original_aspect_ratio=decrease"
    )
    # Pad against the bottom edge so the visible icon sits on the text baseline.
    filter_parts.append(
        f"pad={target_size}:{target_size}:(ow-iw)/2:(oh-ih):color=black@0"
    )

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = pathlib.Path(tmp.name)

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(inline_path),
                "-vf",
                ",".join(filter_parts),
                "-frames:v",
                "1",
                str(tmp_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        tmp_path.replace(inline_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _detect_crop_spec(image_path: pathlib.Path) -> str | None:
    probe = subprocess.run(
        ["ffmpeg", "-i", str(image_path), "-vf", "bbox", "-f", "null", "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    matches = re.findall(r"crop=([0-9:]+)", probe.stderr)
    if matches:
        return matches[-1]
    return None


def _downsize_with_pillow(logo_path: pathlib.Path, max_dim: int) -> bool:
    try:
        from PIL import Image
    except Exception:
        return False

    with Image.open(logo_path) as image:
        if max(image.size) <= max_dim:
            return True

        image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        image.save(logo_path)

    return True


def _downsize_with_sips(logo_path: pathlib.Path, max_dim: int) -> bool:
    if shutil.which("sips") is None:
        return False

    inspect = subprocess.run(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(logo_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    width_match = re.search(r"pixelWidth:\s+(\d+)", inspect.stdout)
    height_match = re.search(r"pixelHeight:\s+(\d+)", inspect.stdout)
    if not width_match or not height_match:
        raise SystemExit(f"could not determine image dimensions: {logo_path}")

    width = int(width_match.group(1))
    height = int(height_match.group(1))
    if max(width, height) <= max_dim:
        return True

    subprocess.run(
        ["sips", "-Z", str(max_dim), str(logo_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return True


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
        f'{usage_link} <img src="{inline_src}" alt="{alt}" width="{width}" height="{width}" '
        f'style="vertical-align: text-bottom;" />: '
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
    parser.add_argument("--inline-asset-size", type=int, default=256)
    parser.add_argument("--logo-width", type=int, default=120)
    parser.add_argument("--logo-max-dim", type=int, default=240)
    args = parser.parse_args()

    readme_path = pathlib.Path(args.readme)
    usage_path = pathlib.Path(args.usage)

    downsize_logo_asset(usage_path, args.logo_src, args.logo_max_dim)
    normalize_inline_png(readme_path, args.inline_src, args.inline_asset_size)

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
