from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "bin" / "sshx"


def _write_file(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_fake_exec(path: Path, *, log_path: Path, exit_code: int = 0) -> None:
    path.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import os\n"
            "from pathlib import Path\n"
            "import sys\n"
            f"Path({str(log_path)!r}).write_text("
            "json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}),"
            " encoding='utf-8')\n"
            f"raise SystemExit({exit_code})\n"
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def _read_log(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


class SshxCliTest(unittest.TestCase):
    def run_cli(
        self,
        args: list[str],
        *,
        home: Path,
        ssh_bin: Path,
        rsync_bin: Path,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["HOME"] = str(home)
        env["SSHX_SSH_BIN"] = str(ssh_bin)
        env["SSHX_RSYNC_BIN"] = str(rsync_bin)
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_syncs_existing_default_paths_then_opens_ssh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(home / ".zshrc", "export PATH=/usr/local/bin:$PATH\n")
            _write_file(home / ".gitconfig", "[user]\nname = Test User\n")
            _write_file(home / ".config" / "nvim" / "init.lua", "vim.o.number = true\n")

            rsync_log = tmp_path / "rsync.json"
            ssh_log = tmp_path / "ssh.json"
            rsync_bin = tmp_path / "fake-rsync"
            ssh_bin = tmp_path / "fake-ssh"
            _write_fake_exec(rsync_bin, log_path=rsync_log)
            _write_fake_exec(ssh_bin, log_path=ssh_log)

            result = self.run_cli(
                ["-i", "/tmp/custom-key", "devbox"],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)

            rsync_payload = _read_log(rsync_log)
            self.assertEqual(Path(str(rsync_payload["cwd"])).resolve(), home.resolve())
            self.assertEqual(
                rsync_payload["argv"][:4],
                ["-az", "--relative", "-e", f"{ssh_bin} -i /tmp/custom-key"],
            )
            self.assertIn("./.zshrc", rsync_payload["argv"])
            self.assertIn("./.gitconfig", rsync_payload["argv"])
            self.assertIn("./.config/nvim", rsync_payload["argv"])
            self.assertEqual(rsync_payload["argv"][-1], "devbox:~/")

            ssh_payload = _read_log(ssh_log)
            self.assertEqual(
                ssh_payload["argv"],
                ["-i", "/tmp/custom-key", "devbox"],
            )

    def test_supports_extra_paths_and_remote_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(home / ".tmux.conf", "set -g mouse on\n")
            _write_file(home / ".config" / "custom-tool" / "config.toml", "enabled = true\n")

            rsync_log = tmp_path / "rsync.json"
            ssh_log = tmp_path / "ssh.json"
            rsync_bin = tmp_path / "fake-rsync"
            ssh_bin = tmp_path / "fake-ssh"
            _write_fake_exec(rsync_bin, log_path=rsync_log)
            _write_fake_exec(ssh_bin, log_path=ssh_log)

            result = self.run_cli(
                [
                    "--no-defaults",
                    "--path",
                    ".tmux.conf",
                    "--path",
                    ".config/custom-tool",
                    "devbox",
                    "uname",
                    "-a",
                ],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)

            rsync_payload = _read_log(rsync_log)
            self.assertEqual(
                rsync_payload["argv"],
                [
                    "-az",
                    "--relative",
                    "-e",
                    str(ssh_bin),
                    "./.tmux.conf",
                    "./.config/custom-tool",
                    "devbox:~/",
                ],
            )

            ssh_payload = _read_log(ssh_log)
            self.assertEqual(
                ssh_payload["argv"],
                ["devbox", "uname", "-a"],
            )

    def test_missing_explicit_path_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()

            rsync_log = tmp_path / "rsync.json"
            ssh_log = tmp_path / "ssh.json"
            rsync_bin = tmp_path / "fake-rsync"
            ssh_bin = tmp_path / "fake-ssh"
            _write_fake_exec(rsync_bin, log_path=rsync_log)
            _write_fake_exec(ssh_bin, log_path=ssh_log)

            result = self.run_cli(
                ["--no-defaults", "--path", ".missing", "devbox"],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing local path", result.stderr)
            self.assertFalse(rsync_log.exists())
            self.assertFalse(ssh_log.exists())

    def test_rsync_failure_stops_before_ssh(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(home / ".zshrc", "export PATH=/usr/local/bin:$PATH\n")

            rsync_log = tmp_path / "rsync.json"
            ssh_log = tmp_path / "ssh.json"
            rsync_bin = tmp_path / "fake-rsync"
            ssh_bin = tmp_path / "fake-ssh"
            _write_fake_exec(rsync_bin, log_path=rsync_log, exit_code=23)
            _write_fake_exec(ssh_bin, log_path=ssh_log)

            result = self.run_cli(
                ["devbox"],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
            )

            self.assertEqual(result.returncode, 23)
            self.assertIn("rsync failed with exit code 23", result.stderr)
            self.assertTrue(rsync_log.exists())
            self.assertFalse(ssh_log.exists())


if __name__ == "__main__":
    unittest.main()
