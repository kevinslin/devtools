from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "sshx" / "bin" / "sshx"
DEFAULT_PROFILE_PATHS = (
    ".bashrc",
    ".codex/agents",
    ".codex/config.toml",
    ".codex/hooks",
    ".codex/hooks.json",
    ".codex/rules",
    ".codex/skills",
    ".profile",
    ".zlogin",
    ".zprofile",
    ".zshenv",
    ".zshrc",
    ".gitconfig",
    ".git.scmbrc",
    ".scmbrc",
    ".tmux.conf",
    ".vimrc",
    ".config/fish",
    ".config/git",
    ".config/iterm2",
    ".config/nvim",
    ".config/uv",
)


def _write_file(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_profile_config(
    path: Path,
    *,
    default_paths: tuple[str, ...] = DEFAULT_PROFILE_PATHS,
    work_paths: tuple[str, ...] | None = None,
) -> None:
    if work_paths is None:
        work_paths = tuple(item for item in default_paths if item != ".zshrc")
    lines = ["profiles:", "  default:"]
    lines.extend(f"    - {item}" for item in default_paths)
    if work_paths:
        lines.append("  work:")
        lines.extend(f"    - {item}" for item in work_paths)
    _write_file(path, "\n".join(lines) + "\n")


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


def _write_retrying_fake_exec(
    path: Path,
    *,
    log_path: Path,
    state_path: Path,
    initial_exit_code: int,
    subsequent_exit_code: int = 0,
) -> None:
    path.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import json\n"
            "import os\n"
            "from pathlib import Path\n"
            "import sys\n"
            f"log_path = Path({str(log_path)!r})\n"
            f"state_path = Path({str(state_path)!r})\n"
            "if state_path.exists():\n"
            "    count = int(state_path.read_text(encoding='utf-8'))\n"
            "else:\n"
            "    count = 0\n"
            "state_path.write_text(str(count + 1), encoding='utf-8')\n"
            "log_path.write_text(\n"
            "    json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd(), 'count': count + 1}),\n"
            "    encoding='utf-8',\n"
            ")\n"
            f"raise SystemExit({initial_exit_code} if count == 0 else {subsequent_exit_code})\n"
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


def _write_fake_ssh_remote_shell(path: Path, *, remote_home: Path) -> None:
    path.write_text(
        (
            "#!/usr/bin/env python3\n"
            "import os\n"
            "from pathlib import Path\n"
            "import subprocess\n"
            "import sys\n"
            "argv = sys.argv[1:]\n"
            "if argv and 'tar -xzf' in argv[-1]:\n"
            "    env = os.environ.copy()\n"
            f"    env['HOME'] = {str(remote_home)!r}\n"
            "    result = subprocess.run(\n"
            "        ['/bin/sh', '-c', argv[-1]],\n"
            "        env=env,\n"
            "        stdin=sys.stdin.buffer,\n"
            "        check=False,\n"
            "    )\n"
            "    raise SystemExit(result.returncode)\n"
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
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        default_config_path = home / ".config" / "sshx" / "config.yaml"
        if not default_config_path.exists():
            _write_profile_config(default_config_path)
        env = os.environ.copy()
        env["HOME"] = str(home)
        env.pop("SSHX_CONFIG_PATH", None)
        env.pop("XDG_CONFIG_HOME", None)
        env["SSHX_SSH_BIN"] = str(ssh_bin)
        env["SSHX_RSYNC_BIN"] = str(rsync_bin)
        if tar_bin is not None:
            env["SSHX_TAR_BIN"] = str(tar_bin)
        if extra_env is not None:
            env.update(extra_env)
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

    def test_profile_paths_can_be_loaded_from_yaml_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(home / ".custom-default", "default\n")
            _write_file(home / ".custom-work", "work\n")
            config_path = tmp_path / "config.yaml"
            _write_file(
                config_path,
                (
                    "profiles:\n"
                    "  default:\n"
                    "    - .custom-default\n"
                    "  work:\n"
                    "    - .custom-work\n"
                ),
            )

            rsync_bin = tmp_path / "fake-rsync"
            ssh_bin = tmp_path / "fake-ssh"

            default_result = self.run_cli(
                ["--dry-run", "--sync-method", "rsync", "devbox"],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
                extra_env={"SSHX_CONFIG_PATH": str(config_path)},
            )

            self.assertEqual(default_result.returncode, 0, msg=default_result.stderr)
            self.assertIn("./.custom-default", default_result.stdout)
            self.assertNotIn("./.custom-work", default_result.stdout)

            work_result = self.run_cli(
                [
                    "--dry-run",
                    "--sync-method",
                    "rsync",
                    "--profile",
                    "work",
                    "devbox",
                ],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
                extra_env={"SSHX_CONFIG_PATH": str(config_path)},
            )

            self.assertEqual(work_result.returncode, 0, msg=work_result.stderr)
            self.assertIn("./.custom-work", work_result.stdout)
            self.assertNotIn("./.custom-default", work_result.stdout)

    def test_xdg_config_home_overrides_default_config_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(home / ".home-profile", "home\n")
            _write_file(home / ".xdg-profile", "xdg\n")
            _write_profile_config(
                home / ".config" / "sshx" / "config.yaml",
                default_paths=(".home-profile",),
            )
            config_home = tmp_path / "xdg-config"
            _write_profile_config(
                config_home / "sshx" / "config.yaml",
                default_paths=(".xdg-profile",),
            )

            result = self.run_cli(
                ["--dry-run", "--sync-method", "rsync", "devbox"],
                home=home,
                ssh_bin=tmp_path / "fake-ssh",
                rsync_bin=tmp_path / "fake-rsync",
                extra_env={"XDG_CONFIG_HOME": str(config_home)},
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("./.xdg-profile", result.stdout)
            self.assertNotIn("./.home-profile", result.stdout)

    def test_explicit_config_path_overrides_xdg_config_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(home / ".xdg-profile", "xdg\n")
            _write_file(home / ".explicit-profile", "explicit\n")
            config_home = tmp_path / "xdg-config"
            _write_profile_config(
                config_home / "sshx" / "config.yaml",
                default_paths=(".xdg-profile",),
            )
            explicit_config_path = tmp_path / "explicit.yaml"
            _write_profile_config(
                explicit_config_path,
                default_paths=(".explicit-profile",),
            )

            result = self.run_cli(
                ["--dry-run", "--sync-method", "rsync", "devbox"],
                home=home,
                ssh_bin=tmp_path / "fake-ssh",
                rsync_bin=tmp_path / "fake-rsync",
                extra_env={
                    "XDG_CONFIG_HOME": str(config_home),
                    "SSHX_CONFIG_PATH": str(explicit_config_path),
                },
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("./.explicit-profile", result.stdout)
            self.assertNotIn("./.xdg-profile", result.stdout)

    def test_missing_config_reports_expected_path_and_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            config_home = tmp_path / "missing-config"

            result = self.run_cli(
                ["--dry-run", "devbox"],
                home=home,
                ssh_bin=tmp_path / "fake-ssh",
                rsync_bin=tmp_path / "fake-rsync",
                extra_env={"XDG_CONFIG_HOME": str(config_home)},
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("sshx config not found", result.stderr)
            self.assertIn(str(config_home / "sshx" / "config.yaml"), result.stderr)
            self.assertIn("SSHX_CONFIG_PATH", result.stderr)

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

    def test_rsync_transport_error_retries_once_before_connecting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            home.mkdir()
            _write_file(home / ".zshrc", "export PATH=/usr/local/bin:$PATH\n")

            rsync_log = tmp_path / "rsync.json"
            rsync_state = tmp_path / "rsync-count.txt"
            ssh_log = tmp_path / "ssh.json"
            rsync_bin = tmp_path / "fake-rsync"
            ssh_bin = tmp_path / "fake-ssh"
            _write_retrying_fake_exec(
                rsync_bin,
                log_path=rsync_log,
                state_path=rsync_state,
                initial_exit_code=255,
            )
            _write_fake_exec(ssh_bin, log_path=ssh_log)

            result = self.run_cli(
                ["--sync-method", "rsync", "devbox"],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=rsync_bin,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("retrying once", result.stderr)
            self.assertEqual(rsync_state.read_text(encoding="utf-8"), "2")
            self.assertTrue(ssh_log.exists())

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
                ssh_calls[0],
                {
                    "argv": [
                        "-n",
                        "devbox",
                        "command -v rsync >/dev/null 2>&1",
                    ],
                    "cwd": str(ROOT),
                    "stdin_len": 0,
                },
            )
            self.assertEqual(ssh_calls[1]["argv"][:1], ["devbox"])
            self.assertIn("mktemp -d", ssh_calls[1]["argv"][-1])
            self.assertIn("tar -xzf -", ssh_calls[1]["argv"][-1])
            self.assertEqual(ssh_calls[1]["cwd"], str(ROOT))
            self.assertEqual(ssh_calls[1]["stdin_len"], len(b"tar-data"))
            self.assertEqual(
                ssh_calls[2],
                {
                    "argv": ["devbox"],
                    "cwd": str(ROOT),
                    "stdin_len": 0,
                },
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

    def test_tar_sync_replaces_remote_directory_with_local_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            home = tmp_path / "home"
            remote_home = tmp_path / "remote-home"
            local_skills = home / ".codex" / "skills"
            remote_skills = remote_home / ".codex" / "skills"
            local_skills.mkdir(parents=True)
            remote_skills.mkdir(parents=True)
            (local_skills / "habitat-cli").symlink_to(
                "../../code/openai/skills/skills/habitat-cli"
            )
            _write_file(remote_skills / "habitat-cli" / "SKILL.md", "old copy\n")
            _write_file(remote_skills / "remote-only" / "SKILL.md", "preserve me\n")

            ssh_bin = tmp_path / "fake-ssh"
            _write_fake_ssh_remote_shell(ssh_bin, remote_home=remote_home)

            result = self.run_cli(
                [
                    "--sync-method",
                    "tar",
                    "--no-defaults",
                    "--path",
                    ".codex/skills",
                    "devbox",
                    "true",
                ],
                home=home,
                ssh_bin=ssh_bin,
                rsync_bin=tmp_path / "unused-rsync",
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            remote_habitat = remote_skills / "habitat-cli"
            self.assertTrue(remote_habitat.is_symlink())
            self.assertEqual(
                os.readlink(remote_habitat),
                "../../code/openai/skills/skills/habitat-cli",
            )
            self.assertEqual(
                (remote_skills / "remote-only" / "SKILL.md").read_text(
                    encoding="utf-8"
                ),
                "preserve me\n",
            )


if __name__ == "__main__":
    unittest.main()
