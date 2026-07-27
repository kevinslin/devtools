from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "cozy"


class CozyCliTest(unittest.TestCase):
    def run_cli(
        self,
        *args: str,
        cwd: Path = ROOT,
        config: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.setdefault("GOCACHE", "/Users/kevinlin/.cache/cozy-go-build")
        if config is not None:
            env["COZY_CONFIG"] = str(config)
        else:
            env.pop("COZY_CONFIG", None)
        return subprocess.run(
            [str(CLI), *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_launcher_is_executable_and_shows_help(self) -> None:
        self.assertTrue(CLI.is_file())
        self.assertTrue(os.access(CLI, os.X_OK))

        result = self.run_cli("--help")

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Usage: cozy", result.stdout)
        self.assertIn("refresh", result.stdout)
        self.assertIn("restart", result.stdout)

    def test_check_honors_explicit_config_from_original_working_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            config = directory / "custom.yaml"
            config.write_text(
                "version: 1\n"
                "sites:\n"
                "  - name: example.localhost\n"
                "    url: http://example.localhost\n"
                "    run: example-server\n",
                encoding="utf-8",
            )

            result = self.run_cli(
                "check",
                "--listen",
                "127.0.0.1:0",
                "--state-dir",
                str(directory / "runtime"),
                cwd=directory,
                config=config,
            )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Configuration is valid", result.stdout)
        self.assertIn("127.0.0.1:0", result.stdout)

    def test_launcher_preserves_unknown_command_and_exit_status(self) -> None:
        result = self.run_cli("not-a-cozy-command")

        self.assertEqual(result.returncode, 2)
        self.assertIn('unknown command "not-a-cozy-command"', result.stderr)

    def test_launcher_preserves_config_error_and_exit_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            missing_config = directory / "missing.yaml"

            result = self.run_cli(
                "check",
                "--listen",
                "127.0.0.1:0",
                "--state-dir",
                str(directory / "runtime"),
                config=missing_config,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("missing.yaml", result.stderr)


if __name__ == "__main__":
    unittest.main()
