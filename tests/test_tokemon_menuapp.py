from __future__ import annotations

import plistlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "tokemon-menuapp"


@unittest.skipUnless(shutil.which("swiftc") and shutil.which("xcrun"), "Swift toolchain required")
class TokemonMenuAppTest(unittest.TestCase):
    def test_builds_menu_app_bundle_with_bundled_tokemon_cli(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_app = Path(tmp) / "Tokemon.app"
            result = subprocess.run(
                [str(CLI), "--output", str(output_app), "--no-open"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertTrue((output_app / "Contents" / "MacOS" / "Tokemon").exists())
            self.assertTrue((output_app / "Contents" / "Resources" / "bin" / "tokemon").exists())
            self.assertIn(str(output_app), result.stdout)

            with (output_app / "Contents" / "Info.plist").open("rb") as handle:
                info = plistlib.load(handle)

            self.assertEqual(info["CFBundleExecutable"], "Tokemon")
            self.assertEqual(info["CFBundleIdentifier"], "com.kevinlin.devtools.tokemon")
            self.assertTrue(info["LSUIElement"])
