from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "epoch"


class EpochCliTest(unittest.TestCase):
    def run_cli(
        self,
        *args: str,
        now: str = "1777242315789.2769",
        timezone_name: str = "America/Los_Angeles",
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["TOOL_EPOCH_NOW"] = now
        env["TZ"] = timezone_name
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_converts_millisecond_epoch_to_utc_local_and_relative_time(self) -> None:
        result = self.run_cli("1777241775789.2769")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "UTC: Sunday, April 26, 2026 at 10:16:15.789 PM",
                "Local: Sunday, April 26, 2026 at 3:16:15.789 PM GMT-07:00 DST",
                "Relative: 9 minutes ago",
            ],
        )

    def test_converts_seconds_epoch(self) -> None:
        result = self.run_cli("1777241775.789")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("UTC: Sunday, April 26, 2026 at 10:16:15.789 PM", result.stdout)

    def test_formats_future_relative_time(self) -> None:
        result = self.run_cli("1777242375789", now="1777242315789")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Relative: in 1 minute", result.stdout)

    def test_rejects_invalid_epoch(self) -> None:
        result = self.run_cli("not-a-time")

        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid epoch timestamp", result.stderr)


if __name__ == "__main__":
    unittest.main()
