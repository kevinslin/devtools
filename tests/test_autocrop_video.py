from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "autocrop-video"


def _make_fixture(path: Path) -> None:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=0x161616:s=640x360:d=4:r=24",
        "-f",
        "lavfi",
        "-i",
        "testsrc2=s=360x200:d=4:r=24",
        "-filter_complex",
        (
            "[0:v]"
            "drawbox=x=0:y=0:w=640:h=44:color=0x2f2f2f:t=fill,"
            "drawbox=x=0:y=44:w=96:h=316:color=0x234f7d:t=fill,"
            "drawbox=x=500:y=44:w=140:h=316:color=0x1f1f1f:t=fill[bg];"
            "[bg][1:v]overlay=120:70:shortest=1"
        ),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    subprocess.run(command, check=True)


def _probe_dimensions(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    stream = payload["streams"][0]
    return int(stream["width"]), int(stream["height"])


class AutocropVideoCliTest(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_detect_reports_expected_bounding_box(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture = tmp_path / "fixture.mp4"
            _make_fixture(fixture)

            result = self.run_cli("detect", str(fixture))

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            bbox = payload["bbox"]
            self.assertAlmostEqual(bbox["x"], 120, delta=10)
            self.assertAlmostEqual(bbox["y"], 70, delta=10)
            self.assertAlmostEqual(bbox["width"], 360, delta=10)
            self.assertAlmostEqual(bbox["height"], 200, delta=10)
            self.assertEqual(
                payload["crop_filter"],
                f"crop={bbox['width']}:{bbox['height']}:{bbox['x']}:{bbox['y']}",
            )

    def test_crop_writes_cropped_video_with_expected_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            fixture = tmp_path / "fixture.mp4"
            output = tmp_path / "cropped.mp4"
            _make_fixture(fixture)

            result = self.run_cli(
                "crop",
                str(fixture),
                str(output),
                "--overwrite",
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertTrue(output.exists())
            width, height = _probe_dimensions(output)
            self.assertAlmostEqual(width, 360, delta=10)
            self.assertAlmostEqual(height, 200, delta=10)


if __name__ == "__main__":
    unittest.main()
