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


def _write_fake_tar(path: Path, *, log_path: Path, payload: bytes = b"archive") -> None:
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
            f"sys.stdout.buffer.write({payload!r})\n"
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_fake_ssh_append(
    path: Path,
    *,
    log_path: Path,
    rsync_available: bool = True,
) -> None:
    path.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import os\n"
            "from pathlib import Path\n"
            "import sys\n"
            "argv = sys.argv[1:]\n"
            "stdin_len = 0\n"
            "if argv and 'tar -xzf' in argv[-1]:\n"
            "    stdin_len = len(sys.stdin.buffer.read())\n"
            "payload = {'argv': argv, 'cwd': os.getcwd(), 'stdin_len': stdin_len}\n"
            f"log_path = Path({str(log_path)!r})\n"
            "calls = json.loads(log_path.read_text(encoding='utf-8')) if log_path.exists() else []\n"
            "calls.append(payload)\n"
            "log_path.write_text(json.dumps(calls), encoding='utf-8')\n"
            "if argv and argv[-1] == 'command -v rsync >/dev/null 2>&1':\n"
            f"    raise SystemExit({0 if rsync_available else 1})\n"
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)


def _read_log(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_calls(path: Path) -> list[dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _expected_tar_args(*paths: str) -> list[str]:
    metadata_flags = (
        ["--no-xattrs", "--no-mac-metadata"] if sys.platform == "darwin" else []
    )
    return ["-czf", "-", *metadata_flags, "--", *paths]


class SshxCliTest(unittest.TestCase):
    def run_cli(
        self,
        args: list[str],
        *,
        home: Path,
        ssh_bin: Path,
        rsync_bin: Path,
        tar_bin: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["HOME"] = str(home)
        env["SSHX_SSH_BIN"] = str(ssh_bin)
        env["SSHX_RSYNC_BIN"] = str(rsync_bin)
        if tar_bin is not None:
            env["SSHX_TAR_BIN"] = str(tar_bin)
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
            _write_file(home / ".codex" / "agents" / "assistant.md", "# assistant\n")
            _write_file(home / ".codex" / "config.toml", "model = \"gpt-5\"\n")
            _write_file(home / ".codex" / "hooks" / "gh_action_check.py", "#!/usr/bin/env python3\n")
            _write_file(home / ".codex" / "hooks.json", "{\n  \"hooks\": []\n}\n")
            _write_file(home / ".codex" / "rules" / "default.md", "# rules\n")
            _write_file(home / ".codex" / "skills" / "demo" / "SKILL.md", "# demo\n")
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
            self.assertIn("./.codex/agents", rsync_payload["argv"])
            self.assertIn("./.codex/config.toml", rsync_payload["argv"])
            self.assertIn("./.codex/hooks", rsync_payload["argv"])
            self.assertIn("./.codex/hooks.json", rsync_payload["argv"])
            self.assertIn("./.codex/rules", rsync_payload["argv"])
            self.assertIn("./.codex/skills", rsync_payload["argv"])
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

    def test_work_profile_excludes_zshrc_from_default_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(home / ".zshrc", "export PATH=/usr/local/bin:$PATH\n")
            _write_file(home / ".gitconfig", "[user]\nname = Work User\n")
            _write_file(home / ".codex" / "config.toml", "model = \"gpt-5\"\n")

            rsync_log = tmp_path / "rsync.json"
            ssh_log = tmp_path / "ssh.json"
            rsync_bin = tmp_path / "fake-rsync"
            ssh_bin = tmp_path / "fake-ssh"
            _write_fake_exec(rsync_bin, log_path=rsync_log)
            _write_fake_exec(ssh_bin, log_path=ssh_log)

            result = self.run_cli(
                ["--profile", "work", "devbox"],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)

            rsync_payload = _read_log(rsync_log)
            self.assertNotIn("./.zshrc", rsync_payload["argv"])
            self.assertIn("./.gitconfig", rsync_payload["argv"])
            self.assertIn("./.codex/config.toml", rsync_payload["argv"])

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
                ["--sync-method", "rsync", "devbox"],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
            )

            self.assertEqual(result.returncode, 23)
            self.assertIn("rsync failed with exit code 23", result.stderr)
            self.assertTrue(rsync_log.exists())
            self.assertFalse(ssh_log.exists())

    def test_auto_falls_back_to_tar_when_remote_rsync_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(home / ".zshrc", "export PATH=/usr/local/bin:$PATH\n")

            rsync_log = tmp_path / "rsync.json"
            tar_log = tmp_path / "tar.json"
            ssh_log = tmp_path / "ssh.json"
            rsync_bin = tmp_path / "fake-rsync"
            tar_bin = tmp_path / "fake-tar"
            ssh_bin = tmp_path / "fake-ssh"
            _write_fake_exec(rsync_bin, log_path=rsync_log, exit_code=127)
            _write_fake_tar(tar_bin, log_path=tar_log, payload=b"tar-data")
            _write_fake_ssh_append(
                ssh_bin,
                log_path=ssh_log,
                rsync_available=False,
            )

            result = self.run_cli(
                ["devbox"],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
                tar_bin=tar_bin,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("falling back to tar-over-ssh sync", result.stderr)
            self.assertFalse(rsync_log.exists())

            tar_payload = _read_log(tar_log)
            self.assertEqual(Path(str(tar_payload["cwd"])).resolve(), home.resolve())
            self.assertEqual(
                tar_payload["argv"],
                _expected_tar_args(".zshrc"),
            )

            ssh_calls = _read_calls(ssh_log)
            self.assertEqual(
                ssh_calls,
                [
                    {
                        "argv": [
                            "-n",
                            "devbox",
                            "command -v rsync >/dev/null 2>&1",
                        ],
                        "cwd": str(ROOT),
                        "stdin_len": 0,
                    },
                    {
                        "argv": [
                            "devbox",
                            'mkdir -p "$HOME" && tar -xzf - -C "$HOME"',
                        ],
                        "cwd": str(ROOT),
                        "stdin_len": len(b"tar-data"),
                    },
                    {
                        "argv": ["devbox"],
                        "cwd": str(ROOT),
                        "stdin_len": 0,
                    },
                ],
            )

    def test_tar_sync_method_skips_rsync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(home / ".gitconfig", "[user]\nname = Test User\n")

            rsync_log = tmp_path / "rsync.json"
            tar_log = tmp_path / "tar.json"
            ssh_log = tmp_path / "ssh.json"
            rsync_bin = tmp_path / "fake-rsync"
            tar_bin = tmp_path / "fake-tar"
            ssh_bin = tmp_path / "fake-ssh"
            _write_fake_exec(rsync_bin, log_path=rsync_log, exit_code=23)
            _write_fake_tar(tar_bin, log_path=tar_log)
            _write_fake_ssh_append(ssh_bin, log_path=ssh_log)

            result = self.run_cli(
                ["--sync-method", "tar", "devbox", "uname", "-a"],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
                tar_bin=tar_bin,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertFalse(rsync_log.exists())
            tar_payload = _read_log(tar_log)
            self.assertEqual(tar_payload["argv"], _expected_tar_args(".gitconfig"))
            ssh_calls = _read_calls(ssh_log)
            self.assertEqual(
                ssh_calls[-1]["argv"],
                ["devbox", "uname", "-a"],
            )


if __name__ == "__main__":
    unittest.main()
