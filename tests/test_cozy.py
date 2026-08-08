from __future__ import annotations

import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "cozy"
GO_CACHE = Path("/Users/kevinlin/.cache/cozy-go-build")


class CozyCliTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.home = Path(temporary_directory.name) / "home"
        self.home.mkdir()
        self.default_config = self.home / ".config" / "cozy" / "config.yaml"
        self.write_config(self.default_config)
        self.launch_agent = (
            self.home / "Library" / "LaunchAgents" / "com.kevinlin.cozy.plist"
        )
        self.launch_agent.parent.mkdir(parents=True)
        agent = {
            "Label": "com.kevinlin.cozy",
            "ProgramArguments": [
                str(CLI),
                "__serve",
                "--config",
                str(self.default_config),
                "--listen",
                "127.0.0.1:8080",
            ],
            "WorkingDirectory": str(ROOT),
            "RunAtLoad": True,
            "KeepAlive": True,
            "ExitTimeOut": 15,
            "EnvironmentVariables": {
                "PATH": os.pathsep.join([str(ROOT / "bin"), "/usr/bin", "/bin"]),
                "GOCACHE": str(GO_CACHE),
            },
            "StandardOutPath": str(
                self.home / "Library" / "Logs" / "com.kevinlin.cozy.log"
            ),
            "StandardErrorPath": str(
                self.home / "Library" / "Logs" / "com.kevinlin.cozy.error.log"
            ),
        }
        with self.launch_agent.open("wb") as destination:
            plistlib.dump(agent, destination)

    def write_config(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "version: 1\n"
            "sites:\n"
            "  - name: agtask.localhost\n"
            "    url: http://agtask.localhost\n"
            f"    run: {CLI} __agtask_dashboard\n",
            encoding="utf-8",
        )

    def run_cli(
        self,
        *args: str,
        cwd: Path = ROOT,
        config: Path | None = None,
        xdg_config_home: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["HOME"] = str(self.home)
        env.setdefault("GOCACHE", str(GO_CACHE))
        env.setdefault("XDG_CACHE_HOME", "/Users/kevinlin/.cache")
        if xdg_config_home is not None:
            env["XDG_CONFIG_HOME"] = str(xdg_config_home)
        else:
            env.pop("XDG_CONFIG_HOME", None)
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

    def test_default_agtask_site_uses_the_existing_launcher(self) -> None:
        configuration = self.default_config.read_text(encoding="utf-8")
        agtask_site = configuration.split("  - name: agtask.localhost\n", 1)[1]
        dashboard_command = next(
            line.removeprefix("    run: ")
            for line in agtask_site.splitlines()
            if line.startswith("    run: ")
        )
        dashboard_executable = Path(dashboard_command.split(maxsplit=1)[0])

        self.assertEqual(dashboard_executable, CLI)
        self.assertTrue(dashboard_executable.is_file())
        self.assertTrue(os.access(dashboard_executable, os.X_OK))

    def test_check_uses_default_user_configuration(self) -> None:
        result = self.run_cli(
            "check",
            "--listen",
            "127.0.0.1:0",
            "--state-dir",
            str(self.home / "runtime"),
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Configuration is valid", result.stdout)

    def test_check_uses_xdg_configuration_directory(self) -> None:
        config_home = self.home / "custom-config"
        self.write_config(config_home / "cozy" / "config.yaml")

        result = self.run_cli(
            "check",
            "--listen",
            "127.0.0.1:0",
            "--state-dir",
            str(self.home / "runtime"),
            xdg_config_home=config_home,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Configuration is valid", result.stdout)

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

    def test_check_honors_config_flag_over_environment(self) -> None:
        explicit_config = self.home / "explicit.yaml"
        self.write_config(explicit_config)

        result = self.run_cli(
            "check",
            "--config",
            str(explicit_config),
            "--listen",
            "127.0.0.1:0",
            "--state-dir",
            str(self.home / "runtime"),
            config=self.home / "missing-environment.yaml",
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("Configuration is valid", result.stdout)

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

    def test_launch_agent_supervises_the_foreground_cozy_process(self) -> None:
        self.assertTrue(self.launch_agent.is_file())

        with self.launch_agent.open("rb") as source:
            agent = plistlib.load(source)

        self.assertEqual(agent["Label"], "com.kevinlin.cozy")
        self.assertEqual(
            agent["ProgramArguments"],
            [
                str(CLI),
                "__serve",
                "--config",
                str(self.default_config),
                "--listen",
                "127.0.0.1:8080",
            ],
        )
        self.assertEqual(agent["WorkingDirectory"], str(ROOT))
        self.assertTrue(agent["RunAtLoad"])
        self.assertTrue(agent["KeepAlive"])
        self.assertGreaterEqual(agent["ExitTimeOut"], 10)

    def test_launch_agent_can_resolve_managed_service_executables(self) -> None:
        with self.launch_agent.open("rb") as source:
            agent = plistlib.load(source)

        environment = agent["EnvironmentVariables"]
        self.assertIn(str(ROOT / "bin"), environment["PATH"].split(os.pathsep))
        self.assertEqual(
            environment["GOCACHE"],
            str(GO_CACHE),
        )
        self.assertEqual(
            agent["StandardOutPath"],
            str(self.home / "Library" / "Logs" / "com.kevinlin.cozy.log"),
        )
        self.assertEqual(
            agent["StandardErrorPath"],
            str(self.home / "Library" / "Logs" / "com.kevinlin.cozy.error.log"),
        )


if __name__ == "__main__":
    unittest.main()
