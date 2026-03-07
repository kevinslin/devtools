from __future__ import annotations

import json
import os
import plistlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "tokemon-menuapp"
APP_SOURCE = ROOT / "apps" / "tokemon" / "TokemonMenuApp.swift"


@unittest.skipUnless(shutil.which("swiftc") and shutil.which("xcrun"), "Swift toolchain required")
class TokemonMenuAppTest(unittest.TestCase):
    def _sdk_path(self) -> str:
        result = subprocess.run(
            ["xcrun", "--show-sdk-path", "--sdk", "macosx"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        return result.stdout.strip()

    def _build_test_harness(self, output_binary: Path, harness_source: str) -> subprocess.CompletedProcess[str]:
        sdk_path = self._sdk_path()
        harness_path = output_binary.with_suffix(".swift")
        harness_path.write_text(harness_source, encoding="utf-8")
        return subprocess.run(
            [
                "swiftc",
                "-parse-as-library",
                "-D",
                "TOKEMON_TESTING",
                str(APP_SOURCE),
                str(harness_path),
                "-sdk",
                sdk_path,
                "-framework",
                "SwiftUI",
                "-framework",
                "AppKit",
                "-framework",
                "Charts",
                "-o",
                str(output_binary),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

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

    def test_cached_snapshots_render_immediately_while_refresh_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            cache_path = tmp_path / "snapshot-cache.json"
            output_binary = tmp_path / "tokemon-menuapp-cache-test"
            harness_source = """
import Foundation

@main
struct TokemonMenuAppHarness {
    static func main() async {
        do {
            guard let rawCachePath = ProcessInfo.processInfo.environment["TOKEMON_MENUAPP_CACHE_PATH"] else {
                throw NSError(
                    domain: "TokemonMenuAppHarness",
                    code: 1,
                    userInfo: [NSLocalizedDescriptionKey: "missing TOKEMON_MENUAPP_CACHE_PATH"]
                )
            }
            let output = try await TokemonMenuAppTestSupport.runCacheScenario(
                cacheFileURL: URL(fileURLWithPath: rawCachePath)
            )
            FileHandle.standardOutput.write(Data(output.utf8))
        } catch {
            let message = String(describing: error) + "\\n"
            FileHandle.standardError.write(Data(message.utf8))
            Foundation.exit(1)
        }
    }
}
"""
            build_result = self._build_test_harness(output_binary, harness_source)
            self.assertEqual(build_result.returncode, 0, msg=build_result.stderr)

            result = subprocess.run(
                [str(output_binary)],
                cwd=ROOT,
                env={**os.environ, "TOKEMON_MENUAPP_CACHE_PATH": str(cache_path)},
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["initial_today"], 111)
            self.assertEqual(payload["initial_has_timestamp"], 1)
            self.assertEqual(payload["loading_today"], 1)
            self.assertEqual(payload["stale_today"], 111)
            self.assertEqual(payload["fresh_today"], 333)
            self.assertEqual(payload["loading_week"], 1)
            self.assertEqual(payload["stale_week"], 222)
            self.assertEqual(payload["fresh_week"], 444)
            self.assertEqual(payload["reopened_has_timestamp"], 1)
            self.assertEqual(payload["reopened_today"], 333)


if __name__ == "__main__":
    unittest.main()
