from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPOSITORY_ROOT / "scripts" / "install.sh"


class InstallScriptTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repository = self.root / "repository"
        self.home = self.root / "home"
        self.home.mkdir()
        (self.repository / "scripts").mkdir(parents=True)
        self.installer = self.repository / "scripts" / "install.sh"
        shutil.copy2(INSTALLER, self.installer)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def add_executable(self, group: str, project: str, command: str) -> Path:
        executable = self.repository / group / project / "bin" / command
        executable.parent.mkdir(parents=True)
        executable.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
        return executable

    def run_installer(self) -> subprocess.CompletedProcess[str]:
        environment = dict(os.environ)
        environment["HOME"] = str(self.home)
        environment.pop("INSTALL_BIN_DIR", None)
        return subprocess.run(
            ["bash", str(self.installer)],
            cwd=self.repository,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_installs_tool_and_application_commands_idempotently(self) -> None:
        tool = self.add_executable("tools", "example", "example")
        application = self.add_executable("apps", "menu", "menu")

        first = self.run_installer()
        second = self.run_installer()

        self.assertEqual(first.returncode, 0, msg=first.stderr)
        self.assertEqual(second.returncode, 0, msg=second.stderr)
        self.assertEqual((self.home / ".local" / "bin" / "example").resolve(), tool.resolve())
        self.assertEqual(
            (self.home / ".local" / "bin" / "menu").resolve(), application.resolve()
        )
        self.assertIn("Installed 2 commands", second.stdout)

    def test_refuses_to_replace_an_existing_regular_file(self) -> None:
        self.add_executable("tools", "example", "example")
        destination = self.home / ".local" / "bin" / "example"
        destination.parent.mkdir(parents=True)
        destination.write_text("keep me\n", encoding="utf-8")

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refusing to replace existing non-symlink", result.stderr)
        self.assertEqual(destination.read_text(encoding="utf-8"), "keep me\n")

    def test_rejects_duplicate_command_names_before_installing(self) -> None:
        self.add_executable("tools", "first", "shared")
        self.add_executable("apps", "second", "shared")

        result = self.run_installer()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("multiple projects provide the command shared", result.stderr)
        self.assertFalse((self.home / ".local" / "bin").exists())


if __name__ == "__main__":
    unittest.main()
